from unittest.mock import patch, MagicMock
from functools import cmp_to_key
from model.reward_log import cmp_by_type_balance

from pay.batch_payer import BatchPayer
from cli.client_manager import ClientManager
from Constants import (
    CURRENT_TESTNET,
    PUBLIC_NODE_URL,
    RewardsType,
    PRIVATE_SIGNER_URL,
    MUTEZ_PER_TEZ,
    PaymentStatus,
)
from api.provider_factory import ProviderFactory
from config.yaml_baking_conf_parser import BakingYamlConfParser
from model.baking_conf import BakingConf
from calc.service_fee_calculator import ServiceFeeCalculator
from tests.utils import mock_request_get, make_config
from model.rules_model import RulesModel
from NetworkConfiguration import default_network_config_map
from plugins.plugins import PluginManager

from calc.phased_payment_calculator import PhasedPaymentCalculator
from calc.calculate_phaseMapping import CalculatePhaseMapping
from calc.calculate_phaseMerge import CalculatePhaseMerge
from calc.calculate_phaseZeroBalance import CalculatePhaseZeroBalance

node_endpoint = PUBLIC_NODE_URL[CURRENT_TESTNET]
network = {"NAME": CURRENT_TESTNET, "MINIMAL_BLOCK_DELAY": 5}

baking_config = make_config(
    "tz1gtHbmBF3TSebsgJfJPvUB2e9x8EDeNm6V",
    "tz1gtHbmBF3TSebsgJfJPvUB2e9x8EDeNm6V",
    14.99,
    0,
)


PAYOUT_CYCLE = 51
PAYMENT_ADDRESS_BALANCE = int(1000 * MUTEZ_PER_TEZ)


@patch("rpc.rpc_reward_api.requests.get", MagicMock(side_effect=mock_request_get))
@patch(
    "rpc.rpc_reward_api.logger",
    MagicMock(debug=MagicMock(side_effect=print), info=MagicMock(side_effect=print)),
)
@patch(
    "pay.payment_producer.logger",
    MagicMock(debug=MagicMock(side_effect=print), info=MagicMock(side_effect=print)),
)
@patch(
    "calc.phased_payment_calculator.logger",
    MagicMock(debug=MagicMock(side_effect=print), info=MagicMock(side_effect=print)),
)
@patch(
    "pay.batch_payer.logger",
    MagicMock(debug=MagicMock(side_effect=print), info=MagicMock(side_effect=print)),
)
@patch(
    "pay.batch_payer.BatchPayer.get_payment_address_balance",
    MagicMock(return_value=PAYMENT_ADDRESS_BALANCE),
)
def test_batch_payer_total_payout_amount():
    factory = ProviderFactory(provider="prpc")
    parser = BakingYamlConfParser(
        baking_config, None, None, None, None, block_api=factory, api_base_url=None
    )
    parser.parse()
    parser.process()

    cfg_dict = parser.get_conf_obj()
    baking_cfg = BakingConf(cfg_dict)

    srvc_fee_calc = ServiceFeeCalculator(
        baking_cfg.get_full_supporters_set(),
        baking_cfg.get_specials_map(),
        baking_cfg.get_service_fee(),
    )
    rules_model = RulesModel(
        baking_cfg.get_excluded_set_tob(),
        baking_cfg.get_excluded_set_toe(),
        baking_cfg.get_excluded_set_tof(),
        baking_cfg.get_dest_map(),
    )
    payment_calc = PhasedPaymentCalculator(
        baking_cfg.get_founders_map(),
        baking_cfg.get_owners_map(),
        srvc_fee_calc,
        int(baking_cfg.get_min_delegation_amount() * MUTEZ_PER_TEZ),
        rules_model,
    )

    rewardApi = factory.newRewardApi(
        default_network_config_map[CURRENT_TESTNET], baking_cfg.get_baking_address(), ""
    )

    # Simulate logic in payment_producer
    reward_logs = []
    attempts = 0
    exiting = False
    while not exiting and attempts < 2:
        attempts += 1

        # Reward data
        # Fetch cycle 51 of granadanet for tz1gtHbmBF3TSebsgJfJPvUB2e9x8EDeNm6V
        reward_model = rewardApi.get_rewards_for_cycle_map(
            PAYOUT_CYCLE, RewardsType.ACTUAL
        )

        # Calculate rewards - payment_producer.py
        reward_model.computed_reward_amount = reward_model.total_reward_amount
        reward_logs, total_amount = payment_calc.calculate(reward_model)

        # Check total reward amount matches sums of records
        # diff of 1 expected due to floating point arithmetic
        assert (
            total_amount - sum([rl.adjusted_amount for rl in reward_logs if rl.payable])
            <= 1
        )
        exiting = True

    # Merge payments to same address
    phaseMerge = CalculatePhaseMerge()
    reward_logs = phaseMerge.calculate(reward_logs)

    # Handle remapping of payment to alternate address
    phaseMapping = CalculatePhaseMapping()
    reward_logs = phaseMapping.calculate(reward_logs, baking_cfg.get_dest_map())

    # Filter zero-balance addresses based on config
    phaseZeroBalance = CalculatePhaseZeroBalance()
    reward_logs = phaseZeroBalance.calculate(
        reward_logs, baking_cfg.get_reactivate_zeroed()
    )

    # Filter out non-payable items
    reward_logs = [payment_item for payment_item in reward_logs if payment_item.payable]
    reward_logs.sort(key=cmp_to_key(cmp_by_type_balance))

    batch_payer = BatchPayer(
        node_url=node_endpoint,
        pymnt_addr="tz1N4UfQCahHkRShBanv9QP9TnmXNgCaqCyZ",
        clnt_mngr=ClientManager(node_endpoint, PRIVATE_SIGNER_URL),
        delegator_pays_ra_fee=True,
        delegator_pays_xfer_fee=True,
        network_config=network,
        plugins_manager=PluginManager(baking_cfg.get_plugins_conf(), dry_run=True),
        dry_run=True,
    )

    # Do the payment
    (
        _,
        total_attempts,
        total_payout_amount,
        number_future_payable_cycles,
    ) = batch_payer.pay(reward_logs, dry_run=True)

    # Payment does not have status done, paid or injected thus the total payout amount is zero
    assert total_payout_amount == 0
    assert number_future_payable_cycles == 2
    assert total_attempts == 3

    # Check the adjusted amount
    assert reward_logs[0].adjusted_amount == 40418486
    assert reward_logs[1].adjusted_amount == 10581272
    assert reward_logs[2].adjusted_amount == 109732835
    assert reward_logs[3].adjusted_amount == 48362127
    assert reward_logs[4].adjusted_amount == 29116310
