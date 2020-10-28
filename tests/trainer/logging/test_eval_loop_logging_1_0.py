# Copyright The PyTorch Lightning team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Tests to ensure that the training loop works with a dict (1.0)
"""
from pytorch_lightning.core.lightning import LightningModule
import os
import collections
import itertools
import pytest
import numpy as np
import torch

import pytorch_lightning as pl
from pytorch_lightning import Trainer
from pytorch_lightning import callbacks, seed_everything

from tests.base.deterministic_model import DeterministicModel
from tests.base import SimpleModule, BoringModel, RandomDataset


def test__validation_step__log(tmpdir):
    """
    Tests that validation_step can log
    """
    os.environ['PL_DEV_DEBUG'] = '1'

    class TestModel(DeterministicModel):
        def training_step(self, batch, batch_idx):
            acc = self.step(batch, batch_idx)
            acc = acc + batch_idx
            self.log('a', acc, on_step=True, on_epoch=True)
            self.log('a2', 2)

            self.training_step_called = True
            return acc

        def validation_step(self, batch, batch_idx):
            acc = self.step(batch, batch_idx)
            acc = acc + batch_idx
            self.log('b', acc, on_step=True, on_epoch=True)
            self.training_step_called = True

        def backward(self, loss, optimizer, optimizer_idx):
            return LightningModule.backward(self, loss, optimizer, optimizer_idx)

    model = TestModel()
    model.validation_step_end = None
    model.validation_epoch_end = None

    trainer = Trainer(
        default_root_dir=tmpdir,
        limit_train_batches=2,
        limit_val_batches=2,
        max_epochs=2,
        log_every_n_steps=1,
        weights_summary=None,
    )
    trainer.fit(model)

    # make sure all the metrics are available for callbacks
    expected_logged_metrics = {
        'a2',
        'a_step',
        'a_epoch',
        'b_step/epoch_0',
        'b_step/epoch_1',
        'b_epoch',
        'epoch',
    }
    logged_metrics = set(trainer.logged_metrics.keys())
    assert expected_logged_metrics == logged_metrics

    # we don't want to enable val metrics during steps because it is not something that users should do
    # on purpose DO NOT allow step_b... it's silly to monitor val step metrics
    callback_metrics = set(trainer.callback_metrics.keys())
    callback_metrics.remove('debug_epoch')
    expected_cb_metrics = {'a', 'a2', 'b', 'a_epoch', 'b_epoch', 'a_step'}
    assert expected_cb_metrics == callback_metrics


def test__validation_step__step_end__epoch_end__log(tmpdir):
    """
    Tests that validation_step can log
    """
    os.environ['PL_DEV_DEBUG'] = '1'

    class TestModel(DeterministicModel):
        def training_step(self, batch, batch_idx):
            acc = self.step(batch, batch_idx)
            acc = acc + batch_idx
            self.log('a', acc)
            self.log('b', acc, on_step=True, on_epoch=True)
            self.training_step_called = True
            return acc

        def validation_step(self, batch, batch_idx):
            acc = self.step(batch, batch_idx)
            acc = acc + batch_idx
            self.log('c', acc)
            self.log('d', acc, on_step=True, on_epoch=True)
            self.validation_step_called = True
            return acc

        def validation_step_end(self, acc):
            self.validation_step_end_called = True
            self.log('e', acc)
            self.log('f', acc, on_step=True, on_epoch=True)
            return ['random_thing']

        def validation_epoch_end(self, outputs):
            self.log('g', torch.tensor(2, device=self.device), on_epoch=True)
            self.validation_epoch_end_called = True

        def backward(self, loss, optimizer, optimizer_idx):
            return LightningModule.backward(self, loss, optimizer, optimizer_idx)

    model = TestModel()

    trainer = Trainer(
        default_root_dir=tmpdir,
        limit_train_batches=2,
        limit_val_batches=2,
        max_epochs=2,
        log_every_n_steps=1,
        weights_summary=None,
    )
    trainer.fit(model)

    # make sure all the metrics are available for callbacks
    logged_metrics = set(trainer.logged_metrics.keys())
    # uniformize behaviour. When provided on_step=True, on_epoch=True, should return both _step and _epoch
    # for training and testing
    # For testing, extra _epoch-{} should be logged too.
    expected_logged_metrics = {
        'epoch',
        'a',
        'b_step',
        'b_epoch',
        'c',
        'd_step',
        'd_step/epoch_0',
        'd_step/epoch_1',
        'd_epoch',
        'e',
        'f_step',
        'f_step/epoch_0',
        'f_step/epoch_1',
        'f_epoch',
        'g',
    }
    assert expected_logged_metrics == logged_metrics

    progress_bar_metrics = set(trainer.progress_bar_metrics.keys())
    expected_pbar_metrics = set()
    assert expected_pbar_metrics == progress_bar_metrics

    # we don't want to enable val metrics during steps because it is not something that users should do
    callback_metrics = set(trainer.callback_metrics.keys())
    callback_metrics.remove('debug_epoch')
    expected_cb_metrics = {'a', 'b', 'c', 'd', 'e', 'd_step', 'd_epoch', 'b_step', 'b_epoch', 'f_step', 'f_epoch', 'f', 'g'}
    assert expected_cb_metrics == callback_metrics


@pytest.mark.parametrize(['batches', 'log_interval', 'max_epochs'], [(1, 1, 1), (64, 32, 2)])
def test_eval_epoch_logging(tmpdir, batches, log_interval, max_epochs):
    """
    Tests that only training_step can be used
    """
    os.environ['PL_DEV_DEBUG'] = '1'

    class TestModel(BoringModel):
        def validation_epoch_end(self, outputs):
            self.log('c', torch.tensor(2), on_epoch=True, prog_bar=True, logger=True)
            self.log('d/e/f', 2)

    model = TestModel()

    trainer = Trainer(
        default_root_dir=tmpdir,
        limit_train_batches=batches,
        limit_val_batches=batches,
        max_epochs=max_epochs,
        log_every_n_steps=log_interval,
        weights_summary=None,
    )
    trainer.fit(model)

    # make sure all the metrics are available for callbacks
    logged_metrics = set(trainer.logged_metrics.keys())
    expected_logged_metrics = {
        'c',
        'd/e/f',
        'epoch',
    }
    assert logged_metrics == expected_logged_metrics

    pbar_metrics = set(trainer.progress_bar_metrics.keys())
    expected_pbar_metrics = {'c'}
    assert pbar_metrics == expected_pbar_metrics

    callback_metrics = set(trainer.callback_metrics.keys())
    callback_metrics.remove('debug_epoch')
    expected_callback_metrics = set()
    expected_callback_metrics = expected_callback_metrics.union(logged_metrics)
    expected_callback_metrics = expected_callback_metrics.union(pbar_metrics)
    expected_callback_metrics.remove('epoch')
    assert callback_metrics == expected_callback_metrics

    # assert the loggers received the expected number
    assert len(trainer.dev_debugger.logged_metrics) == max_epochs


def test_eval_float_logging(tmpdir):
    """
    Tests that only training_step can be used
    """
    os.environ['PL_DEV_DEBUG'] = '1'

    class TestModel(BoringModel):

        def validation_step(self, batch, batch_idx):
            output = self.layer(batch)
            loss = self.loss(batch, output)
            self.log('a', 12.0)
            return {"x": loss}

    model = TestModel()

    trainer = Trainer(
        default_root_dir=tmpdir,
        limit_train_batches=2,
        limit_val_batches=2,
        max_epochs=1,
        log_every_n_steps=1,
        weights_summary=None,
    )
    trainer.fit(model)

    # make sure all the metrics are available for callbacks
    logged_metrics = set(trainer.logged_metrics.keys())
    expected_logged_metrics = {
        'a',
        'epoch',
    }
    assert logged_metrics == expected_logged_metrics


def test_eval_logging_auto_reduce(tmpdir):
    """
    Tests that only training_step can be used
    """
    seed_everything(1234)

    os.environ['PL_DEV_DEBUG'] = '1'

    class TestModel(BoringModel):
        def on_pretrain_routine_end(self) -> None:
            self.seen_vals = []
            self.manual_epoch_end_mean = None

        def on_validation_epoch_start(self) -> None:
            self.seen_vals = []

        def validation_step(self, batch, batch_idx):
            output = self.layer(batch)
            loss = self.loss(batch, output)
            self.seen_vals.append(loss)
            self.log('val_loss', loss, on_epoch=True, on_step=True, prog_bar=True)
            return {"x": loss}

        def validation_epoch_end(self, outputs) -> None:
            for passed_in, manually_tracked in zip(outputs, self.seen_vals):
                assert passed_in['x'] == manually_tracked
            self.manual_epoch_end_mean = torch.stack([x['x'] for x in outputs]).mean()

    model = TestModel()

    trainer = Trainer(
        default_root_dir=tmpdir,
        limit_train_batches=3,
        limit_val_batches=3,
        max_epochs=1,
        log_every_n_steps=1,
        weights_summary=None,
        checkpoint_callback=callbacks.ModelCheckpoint(dirpath='val_loss')
    )
    trainer.fit(model)

    # make sure all the metrics are available for callbacks
    manual_mean = model.manual_epoch_end_mean
    callback_metrics = set(trainer.callback_metrics.keys())
    assert callback_metrics == {'val_loss_epoch', 'val_loss', 'debug_epoch', 'val_loss_step'}

    # make sure values are correct
    assert trainer.logged_metrics['val_loss_epoch'] == manual_mean
    assert trainer.callback_metrics['val_loss'] == trainer.logged_metrics['val_loss_step/epoch_0']

    # make sure correct values were logged
    logged_val = trainer.dev_debugger.logged_metrics

    # sanity check
    assert logged_val[0]['global_step'] == 0
    assert logged_val[1]['global_step'] == 0

    # 3 val batches
    assert logged_val[2]['val_loss_step/epoch_0'] == model.seen_vals[0]
    assert logged_val[3]['val_loss_step/epoch_0'] == model.seen_vals[1]
    assert logged_val[4]['val_loss_step/epoch_0'] == model.seen_vals[2]

    # epoch mean
    assert logged_val[5]['val_loss_epoch'] == model.manual_epoch_end_mean

    # only those logged
    assert len(logged_val) == 6


@pytest.mark.parametrize(['batches', 'log_interval', 'max_epochs'], [(1, 1, 1), (64, 32, 2)])
def test_eval_epoch_only_logging(tmpdir, batches, log_interval, max_epochs):
    """
    Tests that only test_epoch_end can be used to log, and we return them in the results.
    """

    class TestModel(BoringModel):
        def test_epoch_end(self, outputs):
            self.log('c', torch.tensor(2), on_epoch=True, prog_bar=True, logger=True)
            self.log('d/e/f', 2)

    model = TestModel()

    trainer = Trainer(
        default_root_dir=tmpdir,
        limit_train_batches=batches,
        limit_val_batches=batches,
        max_epochs=max_epochs,
        log_every_n_steps=log_interval,
        weights_summary=None,
    )
    trainer.fit(model)
    results = trainer.test(model)

    expected_result_metrics = {
        'c': torch.tensor(2),
        'd/e/f': 2,
    }
    for result in results:
        assert result == expected_result_metrics


def test_monitor_val_epoch_end(tmpdir):
    epoch_min_loss_override = 0
    model = SimpleModule()
    checkpoint_callback = callbacks.ModelCheckpoint(dirpath=tmpdir, save_top_k=1, monitor="avg_val_loss")
    trainer = Trainer(
        max_epochs=epoch_min_loss_override + 2,
        logger=False,
        checkpoint_callback=checkpoint_callback,
    )
    trainer.fit(model)


def test_log_works_in_val_callback(tmpdir):
    """
    Tests that log can be called within callback
    """
    os.environ['PL_DEV_DEBUG'] = '1'

    class TestCallback(callbacks.Callback):

        # helpers
        count = 1
        choices = [False, True]
        # used to compute expected values
        callback_funcs_called = collections.defaultdict(list)
        funcs_called_count = collections.defaultdict(int)
        funcs_attr = {}

        def make_logging(self, pl_module: pl.LightningModule, func_name, func_idx, on_steps=[], on_epochs=[], prob_bars=[]):
            self.funcs_called_count[func_name] += 1
            for idx, t in enumerate(list(itertools.product(*[on_steps, on_epochs, prob_bars]))):
                # run logging
                on_step, on_epoch, prog_bar = t
                custom_func_name = f"{func_idx}_{idx}_{func_name}"
                pl_module.log(custom_func_name, self.count * func_idx, on_step=on_step, on_epoch=on_epoch, prog_bar=prog_bar)
                # catch information for verification
                self.callback_funcs_called[func_name].append([self.count * func_idx])
                self.funcs_attr[custom_func_name] = {
                    "on_step": on_step,
                    "on_epoch": on_epoch,
                    "prog_bar": prog_bar,
                    "forked": on_step and on_epoch,
                    "func_name": func_name}

                if on_step and on_epoch:
                    self.funcs_attr[f"{custom_func_name}_step"] = {
                        "on_step": True,
                        "on_epoch": False,
                        "prog_bar": prog_bar,
                        "forked": False,
                        "func_name": func_name}

                    self.funcs_attr[f"{custom_func_name}_epoch"] = {
                        "on_step": False,
                        "on_epoch": True,
                        "prog_bar": prog_bar,
                        "forked": False,
                        "func_name": func_name}

        def on_validation_start(self, trainer, pl_module):
            self.make_logging(pl_module, 'on_validation_start', 1, on_steps=self.choices,
                              on_epochs=self.choices, prob_bars=self.choices)

        def on_epoch_start(self, trainer, pl_module):
            self.make_logging(pl_module, 'on_epoch_start', 2, on_steps=self.choices,
                              on_epochs=self.choices, prob_bars=self.choices)

        def on_validation_epoch_start(self, trainer, pl_module):
            self.make_logging(pl_module, 'on_validation_epoch_start', 3, on_steps=self.choices,
                              on_epochs=self.choices, prob_bars=self.choices)

        def on_batch_start(self, trainer, pl_module):
            self.make_logging(pl_module, 'on_batch_start', 4, on_steps=self.choices,
                              on_epochs=self.choices, prob_bars=self.choices)

        def on_validation_batch_start(self, trainer, pl_module, batch, batch_idx, dataloader_idx):
            self.make_logging(pl_module, 'on_validation_batch_start', 5, on_steps=self.choices,
                              on_epochs=self.choices, prob_bars=self.choices)

        def on_batch_end(self, trainer, pl_module):
            self.make_logging(pl_module, 'on_batch_end', 6, on_steps=self.choices,
                              on_epochs=self.choices, prob_bars=self.choices)

        def on_validation_batch_end(self, trainer, pl_module, outputs, batch, batch_idx, dataloader_idx):
            self.make_logging(pl_module, 'on_validation_batch_end', 7, on_steps=self.choices,
                              on_epochs=self.choices, prob_bars=self.choices)
            # used to make sure aggregation works fine.
            # we should obtain func[value * c for c in range(1, max_epochs * limit_validation_batches)])
            # with func = np.mean if on_epoch else func = np.max
            self.count += 1

        def on_epoch_end(self, trainer, pl_module):
            self.make_logging(pl_module, 'on_epoch_end', 8, on_steps=[False],
                              on_epochs=self.choices, prob_bars=self.choices)

        def on_validation_epoch_end(self, trainer, pl_module):
            self.make_logging(pl_module, 'on_validation_epoch_end', 9, on_steps=[False],
                              on_epochs=self.choices, prob_bars=self.choices)

    class TestModel(BoringModel):

        def validation_step(self, batch, batch_idx):
            output = self.layer(batch)
            loss = self.loss(batch, output)
            self.log('val_loss', loss)

    max_epochs = 1
    model = TestModel()
    model.validation_epoch_end = None
    test_callback = TestCallback()

    trainer = Trainer(
        default_root_dir=tmpdir,
        limit_train_batches=0,
        limit_val_batches=4,
        limit_test_batches=0,
        val_check_interval=0.,
        num_sanity_val_steps=0,
        max_epochs=max_epochs,
        callbacks=[test_callback],
    )
    trainer.fit(model)
    trainer.test()

    assert test_callback.funcs_called_count["on_epoch_start"] == 1
    assert test_callback.funcs_called_count["on_batch_start"] == 1
    assert test_callback.funcs_called_count["on_batch_end"] == 1
    assert test_callback.funcs_called_count["on_validation_start"] == 1
    assert test_callback.funcs_called_count["on_validation_epoch_start"] == 1
    assert test_callback.funcs_called_count["on_validation_batch_start"] == 4
    assert test_callback.funcs_called_count["on_validation_batch_end"] == 4
    assert test_callback.funcs_called_count["on_validation_epoch_end"] == 1
    assert test_callback.funcs_called_count["on_epoch_end"] == 1

    # Make sure the func_name exists within callback_metrics. If not, we missed some
    callback_metrics_keys = [*trainer.callback_metrics.keys()]
    for func_name in test_callback.callback_funcs_called.keys():
        is_in = False
        for callback_metrics_key in callback_metrics_keys:
            if func_name in callback_metrics_key:
                is_in = True
        assert is_in, (func_name, callback_metrics_keys)

    # function used to describe expected return logic
    def get_expected_output(func_attr, original_values):

        if func_attr["on_epoch"] and not func_attr["on_step"]:
            # Apply mean on values
            expected_output = np.mean(original_values)
        else:
            # Keep the latest value
            expected_output = np.max(original_values)
        return expected_output

    # Make sure the func_name output equals the average from all logged values when on_epoch true
    # pop extra keys
    trainer.callback_metrics.pop("debug_epoch")
    trainer.callback_metrics.pop("val_loss")
    for func_name, output_value in trainer.callback_metrics.items():
        # not sure how to handle this now
        if "epoch_0" in func_name:
            func_name = '/'.join(func_name.split('/')[:-1])
            continue

        if torch.is_tensor(output_value):
            output_value = output_value.item()
        # get creation attr
        func_attr = test_callback.funcs_attr[func_name]

        # retrived orginal logged values
        original_values = test_callback.callback_funcs_called[func_attr["func_name"]]

        # compute expected output and compare to actual one
        expected_output = get_expected_output(func_attr, original_values)
        assert float(output_value) == float(expected_output)

    for func_name, func_attr in test_callback.funcs_attr.items():
        if func_attr["prog_bar"] and (func_attr["on_step"] or func_attr["on_epoch"]) and not func_attr["forked"]:
            assert func_name in trainer.logger_connector.progress_bar_metrics
        else:
            assert func_name not in trainer.logger_connector.progress_bar_metrics


def test_log_works_in_test_callback(tmpdir):
    """
    Tests that log can be called within callback
    """
    os.environ['PL_DEV_DEBUG'] = '1'

    class TestCallback(callbacks.Callback):

        # helpers
        count = 1
        choices = [False, True]

        # used to compute expected values
        callback_funcs_called = collections.defaultdict(list)
        funcs_called_count = collections.defaultdict(int)
        funcs_attr = {}

        def make_logging(self, pl_module: pl.LightningModule, func_name, func_idx, on_steps=[], on_epochs=[], prob_bars=[]):
            original_func_name = func_name[:]
            self.funcs_called_count[original_func_name] += 1
            for idx, t in enumerate(list(itertools.product(*[on_steps, on_epochs, prob_bars]))):
                # run logging
                func_name = original_func_name[:]
                on_step, on_epoch, prog_bar = t
                custom_func_name = f"{func_idx}_{idx}_{func_name}"

                pl_module.log(custom_func_name, self.count * func_idx, on_step=on_step, on_epoch=on_epoch, prog_bar=prog_bar)

                num_dl_ext = ''
                if pl_module._current_dataloader_idx is not None:
                    dl_idx = pl_module._current_dataloader_idx
                    num_dl_ext = f"/dataloader_idx_{dl_idx}"
                    func_name += num_dl_ext

                # catch information for verification
                self.callback_funcs_called[func_name].append([self.count * func_idx])
                self.funcs_attr[custom_func_name + num_dl_ext] = {
                    "on_step": on_step,
                    "on_epoch": on_epoch,
                    "prog_bar": prog_bar,
                    "forked": on_step and on_epoch,
                    "func_name": func_name}
                if on_step and on_epoch:
                    self.funcs_attr[f"{custom_func_name}_step" + num_dl_ext] = {
                        "on_step": True,
                        "on_epoch": False,
                        "prog_bar": prog_bar,
                        "forked": False,
                        "func_name": func_name}

                    self.funcs_attr[f"{custom_func_name}_epoch" + num_dl_ext] = {
                        "on_step": False,
                        "on_epoch": True,
                        "prog_bar": prog_bar,
                        "forked": False,
                        "func_name": func_name}

        def on_test_start(self, trainer, pl_module):
            self.make_logging(pl_module, 'on_test_start', 1, on_steps=self.choices,
                              on_epochs=self.choices, prob_bars=self.choices)

        def on_epoch_start(self, trainer, pl_module):
            self.make_logging(pl_module, 'on_epoch_start', 2, on_steps=self.choices,
                              on_epochs=self.choices, prob_bars=self.choices)

        def on_test_epoch_start(self, trainer, pl_module):
            self.make_logging(pl_module, 'on_test_epoch_start', 3, on_steps=self.choices,
                              on_epochs=self.choices, prob_bars=self.choices)

        def on_test_batch_start(self, trainer, pl_module, batch, batch_idx, dataloader_idx):
            self.make_logging(pl_module, 'on_test_batch_start', 4, on_steps=self.choices,
                              on_epochs=self.choices, prob_bars=self.choices)

        def on_test_batch_end(self, trainer, pl_module, outputs, batch, batch_idx, dataloader_idx):
            self.make_logging(pl_module, 'on_test_batch_end', 5, on_steps=self.choices,
                              on_epochs=self.choices, prob_bars=self.choices)

            # used to make sure aggregation works fine.
            # we should obtain func[value * c for c in range(1, max_epochs * limit_test_batches)])
            # with func = np.mean if on_epoch else func = np.max
            self.count += 1

        def on_epoch_end(self, trainer, pl_module):
            self.make_logging(pl_module, 'on_epoch_end', 6, on_steps=[False],
                              on_epochs=self.choices, prob_bars=self.choices)

        def on_test_epoch_end(self, trainer, pl_module):
            self.make_logging(pl_module, 'on_test_epoch_end', 7, on_steps=[False],
                              on_epochs=self.choices, prob_bars=self.choices)

    max_epochs = 2
    num_dataloaders = 2

    class TestModel(BoringModel):

        manual_mean = collections.defaultdict(list)

        def test_step(self, batch, batch_idx, dataloader_idx=None):
            output = self.layer(batch)
            loss = self.loss(batch, output)
            self.log('test_loss', loss)
            self.manual_mean[str(dataloader_idx)].append(loss)

        def test_dataloader(self):
            return [torch.utils.data.DataLoader(RandomDataset(32, 64)) for _ in range(num_dataloaders)]

    model = TestModel()
    model.test_epoch_end = None
    test_callback = TestCallback()

    trainer = Trainer(
        default_root_dir=tmpdir,
        limit_train_batches=0,
        limit_val_batches=0,
        limit_test_batches=2,
        val_check_interval=0.,
        num_sanity_val_steps=0,
        max_epochs=max_epochs,
        callbacks=[test_callback],
    )
    trainer.fit(model)
    trainer.test()

    assert test_callback.funcs_called_count["on_test_start"] == 1
    assert test_callback.funcs_called_count["on_epoch_start"] == 2
    assert test_callback.funcs_called_count["on_test_epoch_start"] == 1
    assert test_callback.funcs_called_count["on_test_batch_start"] == 4
    assert test_callback.funcs_called_count["on_test_batch_end"] == 4
    assert test_callback.funcs_called_count["on_epoch_end"] == 2
    assert test_callback.funcs_called_count["on_test_epoch_end"] == 1

    # Make sure the func_name exists within callback_metrics. If not, we missed some
    callback_metrics_keys = [*trainer.callback_metrics.keys()]

    for func_name in test_callback.callback_funcs_called.keys():
        is_in = False
        for callback_metrics_key in callback_metrics_keys:
            if func_name in callback_metrics_key:
                is_in = True
        assert is_in, (func_name, callback_metrics_keys)

    # function used to describe expected return logic
    def get_expected_output(func_attr, original_values):
        # Apply mean on values
        if func_attr["on_epoch"] and not func_attr["on_step"]:
            expected_output = np.mean(original_values)
        else:
            expected_output = np.max(original_values)
        return expected_output

    # Make sure the func_name output equals the average from all logged values when on_epoch true
    # pop extra keys
    assert "debug_epoch" in trainer.callback_metrics
    trainer.callback_metrics.pop("debug_epoch")

    for dl_idx in range(num_dataloaders):
        key = f"test_loss/dataloader_idx_{dl_idx}"
        assert key in trainer.callback_metrics
        assert torch.stack(model.manual_mean[str(dl_idx)]).mean() == trainer.callback_metrics[key]
        trainer.callback_metrics.pop(key)

    for func_name, output_value in trainer.callback_metrics.items():
        # not sure how to handle this now
        if "epoch_1" in func_name:
            func_name = '/'.join(func_name.split('/')[:-1])
            continue

        if torch.is_tensor(output_value):
            output_value = output_value.item()

        # get func attr
        func_attr = test_callback.funcs_attr[func_name]

        # retrived orginal logged values
        original_values = test_callback.callback_funcs_called[func_attr["func_name"]]

        # compute expected output and compare to actual one
        expected_output = get_expected_output(func_attr, original_values)
        assert float(output_value) == float(expected_output)

    for func_name, func_attr in test_callback.funcs_attr.items():
        if func_attr["prog_bar"] and (func_attr["on_step"] or func_attr["on_epoch"]) and not func_attr["forked"]:
            assert func_name in trainer.logger_connector.progress_bar_metrics
        else:
            assert func_name not in trainer.logger_connector.progress_bar_metrics
