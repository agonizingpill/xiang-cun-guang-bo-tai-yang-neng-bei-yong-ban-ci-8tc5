"""本地冒烟/测试用的最小 Redis 替身：仅实现本项目用到的命令。"""


class FakeRedis:
    def __init__(self, *args, **kwargs):
        self.kv = {}
        self.lists = {}

    def ping(self):
        return True

    def set(self, key, value, ex=None):
        self.kv[key] = value

    def get(self, key):
        return self.kv.get(key)

    def rpush(self, key, *values):
        self.lists.setdefault(key, []).extend(values)
        return len(self.lists[key])

    def lpush(self, key, *values):
        for value in values:
            self.lists.setdefault(key, []).insert(0, value)
        return len(self.lists[key])

    def lrange(self, key, start, end):
        items = self.lists.get(key, [])
        if end == -1:
            end = len(items) - 1
        return items[start:end + 1]

    def lrem(self, key, count, value):
        items = self.lists.get(key, [])
        removed = 0
        for _ in range(abs(count) if count else len(items)):
            try:
                items.remove(value)
                removed += 1
            except ValueError:
                break
        return removed

    def blmove(self, src, dest, timeout=0, **kwargs):
        items = self.lists.get(src, [])
        if not items:
            return None
        value = items.pop(0)
        self.lists.setdefault(dest, []).append(value)
        return value

    def pipeline(self):
        class _Pipe:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

            def __getattr__(self_inner, name):
                return getattr(self, name)

            def execute(self_inner):
                return []

        return _Pipe()
