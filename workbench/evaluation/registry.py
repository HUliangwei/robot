_REGISTRY = {}

def register(name, evaluator):
    _REGISTRY[name] = evaluator

def get(name):
    return _REGISTRY[name]
