import typing as tp
from datetime import datetime
from copy import deepcopy

import autograd.numpy as np
from tqdm.auto import tqdm

from .layer import BaseLayer, Dense, WeightsParser, Fuzzify
from .functions import GaussianRBF, ReLU, Tanh, Sigmoid, Linear, BellMembership
from .optimisers import BaseOptimizer
from .utils import gen_batch


class FFN(object):
    def __init__(
        self,
        input_shape: tp.Tuple[int],
        layer_specs: tp.List[BaseLayer],
        loss: tp.Callable[..., np.ndarray],
        **kwargs,
    ) -> None:
        """
        Feed Forward Network
        Args:
            input_shape (int): shape of your `X` variable
            layer_specs (list(BaseLayer)): layer list
            loss (callable): loss function
        """
        self.parser = WeightsParser()
        self.regularization = kwargs.get("regularization", "l2")
        self.reg_coef = kwargs.get("reg_coef", 0)
        self.layer_specs = layer_specs
        cur_shape = input_shape
        W_vect = np.array([])
        for num, layer in enumerate(self.layer_specs):
            layer.number = num
            N_weights, cur_shape = layer.build_weights_dict(cur_shape)
            self.parser.add_weights(str(layer), (N_weights,))
            W_vect = np.append(W_vect, layer.initializer(size=(N_weights,)))
        self._loss = loss
        self.W_vect = 0.1 * W_vect

    def loss(
        self, W_vect: np.ndarray, X: np.ndarray, y: np.ndarray, omit_reg: bool = False
    ):
        if self.regularization == "l2" and not omit_reg:
            reg = np.power(np.linalg.norm(W_vect, 2), 2)
        elif self.regularization == "l1" and not omit_reg:
            reg = np.linalg.norm(W_vect, 1)
        else:
            reg = 0.0
        return self._loss(self._predict(W_vect, X), y) + self.reg_coef * reg

    def predict(self, inputs: np.ndarray) -> np.ndarray:
        return self._predict(self.W_vect, inputs)

    def _predict(self, W_vect: np.ndarray, inputs: np.ndarray) -> np.ndarray:
        cur_units = inputs
        for layer in self.layer_specs:
            cur_weights = self.parser.get(W_vect, str(layer))
            cur_units = layer.forward(cur_units, cur_weights)
        return cur_units

    def eval(self, input: np.ndarray, output: np.ndarray) -> float:
        return self.loss(self.W_vect, input, output, omit_reg=True)

    def frac_err(self, X, T):
        return np.mean(
            np.argmax(T, axis=1) != np.argmax(self.predict(self.W_vect, X), axis=1)
        )

    def fit(
        self,
        optimiser: BaseOptimizer,
        train_sample: tp.Tuple[np.ndarray],
        validation_sample: tp.Tuple[np.ndarray],
        batch_size: int,
        epochs: tp.Optional[int] = None,
        verbose: tp.Optional[bool] = None,
        load_best_model_on_end: bool = True,
        minimize_metric: bool = True,
    ):
        self._optimiser = optimiser

        verbose = verbose if verbose else False
        epochs = epochs if epochs else 1

        inst = None
        best_inst = None
        best_score = np.inf if minimize_metric else -np.inf
        best_epoch = 0

        history = dict(epoch=[], train_loss=[], validation_loss=[])

        for i in tqdm(range(epochs), desc="Training "):

            tr_accum_loss = []
            tr_loss = np.inf
            to_stop = False

            for (X, y) in gen_batch(train_sample, batch_size):
                to_stop, inst, tr_loss = self._optimiser.apply(
                    self.loss, X, y, self.W_vect, verbose=verbose
                )
                self.W_vect = inst
                tr_accum_loss.append(tr_loss)

            tr_accum_loss = np.mean(tr_accum_loss)

            history["epoch"].append(i)
            history["train_loss"].append(tr_accum_loss)

            val_loss = self.eval(*validation_sample)[0]
            history["validation_loss"].append(val_loss)

            if minimize_metric and val_loss < best_score:
                best_score = val_loss
                best_inst = deepcopy(self.W_vect)
                best_epoch = i
            elif (not minimize_metric) and val_loss > best_score:
                best_score = val_loss
                best_inst = deepcopy(self.W_vect)
                best_epoch = i
            else:
                pass

            if verbose:
                print(f"validation loss - {val_loss}")
            if to_stop:
                break

        if load_best_model_on_end:
            self.W_vect = best_inst
            if verbose:
                print(f"best validation loss - {best_score}")
                print(f"best epoch - {best_epoch}")

        return self, history
