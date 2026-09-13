from collections import OrderedDict
from copy import deepcopy
from hashlib import sha256
import json


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class RouteCache:
    def __init__(self, capacity=2048):
        self.capacity, self.items = capacity, OrderedDict()

    def get(self, key):
        if key not in self.items:
            return None
        self.items.move_to_end(key)
        return deepcopy(self.items[key])

    def put(self, key, value):
        self.items[key] = deepcopy(value)
        self.items.move_to_end(key)
        if len(self.items) > self.capacity:
            self.items.popitem(last=False)
