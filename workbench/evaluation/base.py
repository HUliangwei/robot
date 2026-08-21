from abc import ABC, abstractmethod

class Evaluator(ABC):
    @abstractmethod
    def evaluate(self, run_id, artifact):
        raise NotImplementedError
