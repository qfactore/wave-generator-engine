from wave_generator_engine.errors import ValidationFailure


class DensePlanner:
    mode = "dense"

    def plan(self, *args, **kwargs):
        raise ValidationFailure("mode_not_implemented_in_wge3")
