import inspect

import numpy as np
import pytest

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.motifs.identity import ExactIdentityAccess


def test_every_authoritative_array_is_immutable(real_motif_bank) -> None:
    for record in real_motif_bank.records():
        assert not record.samples.flags.writeable
        with pytest.raises(ValueError):
            record.samples.flat[0] = 0


def test_detached_copy_is_explicitly_non_authoritative(real_motif_bank) -> None:
    source = real_motif_bank.records()[0]
    copied, label = source.diagnostic_copy()
    assert copied.flags.writeable
    assert label["authoritative"] is False
    assert label["production_source"] is False
    copied.flat[0] += 1
    assert not np.array_equal(copied, source.samples)


def test_exact_identity_receipt(real_motif_bank) -> None:
    access = ExactIdentityAccess(real_motif_bank)
    record, receipt = access.access(real_motif_bank.ids()[0])
    assert receipt.operations == ()
    assert receipt.exact_bypass
    assert not receipt.randomness_used
    assert not receipt.transform_path_entered
    assert receipt.source_dtype == receipt.result_dtype
    assert receipt.source_shape == receipt.result_shape
    assert receipt.bitwise_equal and receipt.read_only
    assert len(receipt.provenance_references) >= 4
    assert not record.samples.flags.writeable


@pytest.mark.parametrize("parameter", [
    {"gain": 1.1},
    {"sample_rate_hz": 44100},
    {"operations": []},
    {"motif_time_scale_ratio": 1.0},
])
def test_exact_access_rejects_all_operation_parameters(real_motif_bank, parameter) -> None:
    with pytest.raises(ValidationFailure, match="no transform parameters"):
        ExactIdentityAccess(real_motif_bank).access(real_motif_bank.ids()[0], **parameter)


def test_exact_module_has_no_transform_or_random_pipeline() -> None:
    import wave_generator_engine.motifs.identity as identity

    source = inspect.getsource(identity)
    assert "transform_executor" not in source
    assert "np.random" not in source
    assert "default_rng" not in source
    assert "operation_pipeline" not in source
