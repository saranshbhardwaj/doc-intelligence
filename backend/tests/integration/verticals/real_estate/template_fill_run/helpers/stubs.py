class ResultHandle:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


class TaskStub:
    def __init__(self, value):
        self.calls = []
        self._value = value

    def delay(self, **kwargs):
        self.calls.append(kwargs)
        return ResultHandle(self._value)


class DispatchOnlyTaskStub:
    def __init__(self):
        self.calls = []

    def delay(self, **kwargs):
        self.calls.append(kwargs)


class StorageStub:
    def __init__(self):
        self.deleted_keys = []

    def delete(self, key):
        self.deleted_keys.append(key)


class PubSubStub:
    def __init__(self):
        self.closed = False

    def get_message(self, timeout=1.0):
        return None

    def close(self):
        self.closed = True
