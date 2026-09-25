def test_public_contract_imports_remain_identical():
    from starroboharness.contracts import Observation as PublicContract

    from starharness import Observation
    from starroboharness import Observation as PublicObservation

    assert Observation is PublicObservation is PublicContract
