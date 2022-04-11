from log_config import main_logger
import requests
from Constants import DEFAULT_NETWORK_CONFIG_MAP, PUBLIC_NODE_URL

logger = main_logger

default_network_config_map = DEFAULT_NETWORK_CONFIG_MAP

CONSTANTS_PATH = "/chains/main/blocks/head/context/constants"


def init_network_config(network_name, config_client_manager):
    network_config_map = {}
    node_addr = config_client_manager.get_node_url()
    if True:
        network_config_map[network_name] = get_network_config_from_local_node(
            config_client_manager
        )
        network_config_map[network_name]["NAME"] = network_name
        logger.debug(
            "Network configuration constants successfully loaded from local node ({}).".format(
                node_addr
            )
        )
        return network_config_map
    # except Exception:
    #    logger.debug(
    #        "Failed to get network configuration constants from a local node ({}).".format(
    #            node_addr
    #        )
    #    )

    pub_node_url = PUBLIC_NODE_URL[network_name]
    try:
        network_config_map[network_name] = get_network_config_from_public_node(
            network_name
        )
        network_config_map[network_name]["NAME"] = network_name
        logger.debug(
            "Network configuration constants successfully loaded from a public node ({}).".format(
                pub_node_url
            )
        )
        return network_config_map
    except Exception:
        logger.debug(
            "Failed to get network configuration constants from a public node ({}).".format(
                pub_node_url
            )
        )

    logger.debug("Default network configuration constants will be used.")

    return default_network_config_map


def get_network_config_from_local_node(config_client_manager):
    _, response_constants = config_client_manager.request_url(CONSTANTS_PATH)
    network_config_map = parse_constants(response_constants)
    return network_config_map


def get_network_config_from_public_node(network_name):
    url = PUBLIC_NODE_URL[network_name] + CONSTANTS_PATH
    response_constants = requests.get(url, timeout=5)
    constants = response_constants.json()
    logger.info(constants)
    network_config_map = parse_constants(constants)
    return network_config_map


def parse_constants(constants):
    network_config_map = {}
    network_config_map["NB_FREEZE_CYCLE"] = int(constants["preserved_cycles"])
    network_config_map["MINIMAL_BLOCK_DELAY"] = int(constants["minimal_block_delay"])
    network_config_map["BLOCKS_PER_CYCLE"] = int(constants["blocks_per_cycle"])
    network_config_map["BLOCKS_PER_STAKE_SNAPSHOT"] = int(
        constants["blocks_per_stake_snapshot"]
    )
    network_config_map["BLOCK_REWARD"] = int(
        int(constants["baking_reward_fixed_portion"])
        + (
            int(constants["baking_reward_bonus_per_slot"])
            * int(constants["consensus_committee_size"])
            / 3
        )
    )
    network_config_map["CONSENSUS_COMMITTEE_SIZE"] = int(
        constants["consensus_committee_size"]
    )
    network_config_map["ENDORSING_REWARD_PER_SLOT"] = int(
        constants["endorsing_reward_per_slot"]
    )
    return network_config_map
