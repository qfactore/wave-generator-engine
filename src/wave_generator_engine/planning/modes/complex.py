from wave_generator_engine.errors import ValidationFailure


class ComplexPlanner:
    mode = "complex"

    def plan(self, *args, **kwargs):
        raise ValidationFailure("mode_not_implemented_in_wge3")
