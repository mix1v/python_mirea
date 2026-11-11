"""SQLite через PonyORM: сущности и обязательные внешние ключи."""

from pathlib import Path
from contextlib import contextmanager

from pony.orm import Database, Optional, PrimaryKey, Required, Set, db_session

from jpeg_gif.schema import SCHEMA


def define_entities(database):
    """Повторить три сущности рисунка 9 в отдельной базе PonyORM."""
    class Individual(database.Entity):
        key = PrimaryKey(int, auto=True)
        timestamp = Required(int)
        ip = Optional(str, autostrip=False)
        locale = Optional(str, autostrip=False)
        platform = Optional(str, autostrip=False)
        user_agent = Optional(str, autostrip=False)
        assignments = Set("Assignment")

    class Assignment(database.Entity):
        key = PrimaryKey(int, auto=True)
        timestamp = Required(int)
        payload = Optional(str, autostrip=False)
        individual = Required(Individual, column="individual")
        state = Optional(str, autostrip=False)
        enqueued = Required(int)
        responses = Set("Response")

    class Response(database.Entity):
        key = PrimaryKey(int, auto=True)
        timestamp = Required(int)
        response = Optional(str, autostrip=False)
        state = Optional(str, autostrip=False)
        error = Optional(str, autostrip=False)
        assignment = Required(Assignment, column="assignment")
        cache_hit = Required(int)

    return {"individual": Individual, "assignment": Assignment,
            "response": Response}


class PonyStore:
    """Тот же контракт read/insert/update, что и у файлового слоя."""

    def __init__(self, filename):
        path = Path(filename).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.database = Database()
        self.entities = define_entities(self.database)
        self.database.bind(
            provider="sqlite", filename=str(path), create_db=True,
        )
        self.database.generate_mapping(create_tables=True)
        self.database.disconnect()

    @contextmanager
    def _session(self):
        """Закрыть соединение именно того потока, который его открыл."""
        try:
            with db_session:
                yield
        finally:
            self.database.disconnect()

    def _record(self, table, entity):
        result = {}
        for name in SCHEMA[table]:
            value = getattr(entity, name)
            if name in {"individual", "assignment"}:
                value = value.key
            result[name] = value
        return result

    def _values(self, values):
        result = dict(values)
        for name in {"individual", "assignment"} & result.keys():
            result[name] = self.entities[name][result[name]]
        return result

    def read(self, table):
        """Вернуть обычные словари до завершения ORM-сессии."""
        with self._session():
            rows = [self._record(table, row)
                    for row in self.entities[table].select()]
            return sorted(rows, key=lambda row: row["key"])

    def insert(self, table, values):
        """Создать сущность и дать SQLite назначить первичный ключ."""
        with self._session():
            entity = self.entities[table](**self._values(values))
            entity.flush()
            return self._record(table, entity)

    def update(self, table, key, values):
        """Изменить поля сущности внутри транзакции PonyORM."""
        with self._session():
            self.entities[table][key].set(**self._values(values))

    def close(self):
        """Освободить соединение после остановки HTTP и очереди."""
        self.database.disconnect()
