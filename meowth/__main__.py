
import asyncio
import copy
import datetime
import gettext
import io
import json
import os
import pickle
import sys
import tempfile
import textwrap
import time
import traceback
import argparse

from contextlib import redirect_stdout
from time import strftime

import discord
from discord.ext import commands

from meowth import checks, errors, config
from meowth.bot import MeowthBot
from meowth.errors import custom_error_handling
from meowth.logs import init_loggers
from meowth.exts import pokemon as pkmn_class
from meowth.exts import utilities as utils

if discord.version_info.major < 1:
    print("You are not running discord.py v1.0.0a or above.\n\n"
          "Meowth v3 requires the new discord.py library to function "
          "correctly. Please install the correct version.")
    sys.exit(1)

def _get_prefix(bot, message):
    guild = message.guild
    try:
        prefix = bot.guild_dict[guild.id]['configure_dict']['settings']['prefix']
    except (KeyError, AttributeError):
        prefix = None
    if not prefix:
        prefix = bot.default_prefix
    return commands.when_mentioned_or(prefix)(bot, message)

def run_bot(debug=False, launcher=None, from_restart=False):
    """Sets up the bot, runs it and handles exit codes."""

    # create async loop and setup contextvar
    loop = asyncio.get_event_loop()

    # create bot instance
    Meowth = MeowthBot(command_prefix=_get_prefix, launcher=launcher,
    debug=debug, from_restart=from_restart)

    # setup logging
    logger = init_loggers()
    custom_error_handling(Meowth, logger)

    # load the required core modules
    required_exts = ['admin', 'utilities', 'pokemon', 'configure']
    optional_exts = ['want', 'wild', 'raid', 'list', 'gymmatching', 'tutorial', 'silph', 'trade', 'research', 'nest', 'huntr', 'trainers', 'lure', 'pvp']
    meowth_exts = required_exts + optional_exts

    for ext in meowth_exts:
        try:
            Meowth.load_extension(f"meowth.exts.{ext}")
        except Exception as e:
            timestr = time.strftime("%d/%m/%Y %H:%M", time.localtime())
            print(f"--------------------\nEXCEPTION: A {sys.exc_info()[0].__name__} exception has occured when loading {ext} extension. Check outputlog for details.\n[{timestr}]: {sys.exc_info()[1]}\n--------------------")
            logger.exception(f'{traceback.format_exc()}')
        else:
            if 'debug' in sys.argv[1:]:
                print(f'Loaded {ext} extension.')

    # Load serverdict
    try:
        with open(os.path.join('data', 'serverdict'), 'rb') as fd:
            Meowth.guild_dict = pickle.load(fd)
        logger.info('Serverdict Loaded Successfully')
    except OSError:
        logger.info('Serverdict Not Found - Looking for Backup')
        try:
            with open(os.path.join('data', 'serverdict_backup'), 'rb') as fd:
                Meowth.guild_dict = pickle.load(fd)
            logger.info('Serverdict Backup Loaded Successfully')
        except OSError:
            logger.info('Serverdict Backup Not Found - Creating New Serverdict')
            Meowth.guild_dict = {}
            with open(os.path.join('data', 'serverdict'), 'wb') as fd:
                pickle.dump(Meowth.guild_dict, fd, (- 1))
            logger.info('Serverdict Created')

    # Load config
    language = gettext.translation(
        'meowth', localedir='locale', languages=[config.bot_language])
    language.install()
    pokemon_language = [config.pokemon_language]
    pkmn_class.Pokemon.generate_lists(Meowth)
    Meowth.raid_list = utils.get_raidlist(Meowth)

    if Meowth.token is None or not Meowth.default_prefix:
        Meowth.logger.critical(
            "Token and prefix must be set in order to login.")
        sys.exit(1)
    try:
        loop.run_until_complete(Meowth.start(Meowth.token))
    except discord.LoginFailure:
        Meowth.logger.critical("Invalid token")
        loop.run_until_complete(Meowth.logout())
        Meowth._shutdown_mode = 0
    except KeyboardInterrupt:
        Meowth.logger.info("Keyboard interrupt detected. Quitting...")
        loop.run_until_complete(Meowth.logout())
        Meowth._shutdown_mode = 0
    except Exception as exc:
        Meowth.logger.critical("Fatal exception", exc_info=exc)
        loop.run_until_complete(Meowth.logout())
    finally:
        sys.exit(Meowth._shutdown_mode)

def parse_cli_args():
    parser = argparse.ArgumentParser(
        description="Meowth - Discord Bot for Pokemon Go Communities")
    parser.add_argument(
        "--debug", "-d", help="Enabled debug mode.", action="store_true")
    parser.add_argument(
        "--launcher", "-l", help=argparse.SUPPRESS, action="store_true")
    parser.add_argument(
        "--fromrestart", help=argparse.SUPPRESS, action="store_true")
    return parser.parse_known_args()

def main():
    args, unknown = parse_cli_args()
    run_bot(debug=args.debug, launcher=args.launcher,
        from_restart=args.fromrestart)

if __name__ == '__main__':
    main()
