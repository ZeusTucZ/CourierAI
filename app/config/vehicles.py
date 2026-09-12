from app.models.common import Model, NonNegative, Positive, Vehicle


class VehicleProfile(Model):
    speed_kmh: Positive
    max_weight_kg: Positive
    max_volume_liters: Positive
    operating_cost_mxn_per_km: NonNegative


def default_vehicle_profiles() -> dict[Vehicle, VehicleProfile]:
    # PLACEHOLDERS for calibration, not measured vehicle specifications.
    return {
        "moto": VehicleProfile(speed_kmh=25, max_weight_kg=15, max_volume_liters=50,
                               operating_cost_mxn_per_km=1.2),
        "car": VehicleProfile(speed_kmh=20, max_weight_kg=100, max_volume_liters=300,
                              operating_cost_mxn_per_km=3),
        "bike": VehicleProfile(speed_kmh=15, max_weight_kg=8, max_volume_liters=25,
                               operating_cost_mxn_per_km=0.2),
    }
