from pydantic import BaseModel, ConfigDict


class QPUSpecsResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "specs": {
                    "name": "FRESNEL_CAN1",
                    "dimensions": 2,
                    "rydberg_level": 60,
                    "min_atom_distance": 5,
                    "max_atom_num": 100,
                    "max_radial_distance": 46,
                    "max_sequence_duration": 6000,
                    "max_runs": 1000,
                    "pulser_version": "1.5.4",
                    "channels": [
                        {
                            "id": "rydberg_global",
                            "basis": "ground-rydberg",
                            "addressing": "Global",
                            "max_abs_detuning": 62.83185307179586,
                            "max_amp": 12.566370614359172,
                        }
                    ],
                }
            }
        }
    )
    specs: str
