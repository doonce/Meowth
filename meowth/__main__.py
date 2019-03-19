
import asyncio
import copy
import datetime
import functools
import gettext
import io
import json
import os
import pickle
import re
import sys
import tempfile
import textwrap
import time
import traceback

from contextlib import redirect_stdout
from io import BytesIO
from operator import itemgetter
from time import strftime

import aiohttp
import dateparser
import hastebin
from dateutil import tz
from dateutil.relativedelta import relativedelta

import discord
from discord.ext import commands

from meowth import checks
from meowth import utils
from meowth.bot import MeowthBot
from meowth.errors import custom_error_handling
from meowth.logs import init_loggers
from meowth.exts import pokemon as pkmn_class

logger = init_loggers()

def _get_prefix(bot, message):
    guild = message.guild
    try:
        prefix = bot.guild_dict[guild.id]['configure_dict']['settings']['prefix']
    except (KeyError, AttributeError):
        prefix = None
    if not prefix:
        prefix = bot.config['default_prefix']
    return commands.when_mentioned_or(prefix)(bot, message)

Meowth = MeowthBot(
    command_prefix=_get_prefix, case_insensitive=True,
    activity=discord.Game(name="Pokemon Go"))

Meowth._get_prefix = _get_prefix

custom_error_handling(Meowth, logger)
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

guild_dict = Meowth.guild_dict

config = {}
pkmn_info = {}
type_chart = {}
raid_info = {}

# Append path of this script to the path of
# config files which we're loading.
# Assumes that config files will always live in the same directory.
script_path = os.path.dirname(os.path.realpath(__file__))

"""
Helper functions
"""

def load_config():
    global config
    global pkmn_info
    global type_chart
    global raid_info
    # Load configuration
    with open('config.json', 'r') as fd:
        config = json.load(fd)
    # Set up message catalog access
    language = gettext.translation(
        'meowth', localedir='locale', languages=[config['bot-language']])
    language.install()
    pokemon_language = [config['pokemon-language']]
    pokemon_path_source = os.path.join(
        'locale', '{0}', 'pkmn.json').format(config['pokemon-language'])
    raid_path_source = os.path.join('data', 'raid_info.json')
    # Load Pokemon list and raid info
    with open(pokemon_path_source, 'r', encoding="utf8") as fd:
        pkmn_info = json.load(fd)
    Meowth.pkmn_info = pkmn_info
    with open(raid_path_source, 'r') as fd:
        raid_info = json.load(fd)
    Meowth.raid_info = raid_info
    # Load type information
    with open(os.path.join('data', 'type_chart.json'), 'r') as fd:
        type_chart = json.load(fd)
    Meowth.type_chart = type_chart
    pkmn_list = []
    count = 1
    try:
        pkmn_list = Meowth.pkmn_list
    except AttributeError:
        for k, v in pkmn_info.items():
            if v['number'] == count:
                pkmn_list.append(k)
            count += 1
        Meowth.pkmn_list = pkmn_list
    pkmn_class.Pokemon.generate_lists(Meowth)
    Meowth.raid_list = utils.get_raidlist(Meowth)
    Meowth.pkmn_info_path = pokemon_path_source
    Meowth.raid_json_path = raid_path_source

load_config()

Meowth.config = config
Meowth.load_config = load_config

required_exts = ['utilities', 'pokemon', 'configure']
optional_exts = ['want', 'wild', 'raid', 'list', 'gymmatching', 'tutorial', 'silph', 'trade', 'research', 'nest', 'huntr']
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

"""
Admin Commands
"""

@Meowth.command(name='load')
@checks.is_owner()
async def _load(ctx, *extensions):
    for ext in extensions:
        try:
            if f"meowth.exts.{ext}" in Meowth.extensions:
                ctx.bot.reload_extension(f"meowth.exts.{ext}")
                await ctx.send(_('**Extension {ext} Reloaded.**\n').format(ext=ext))
                return
            ctx.bot.load_extension(f"meowth.exts.{ext}")
            await ctx.send(_('**Extension {ext} Loaded.**\n').format(ext=ext))
        except Exception as e:
            error_title = _('**Error when loading extension')
            await ctx.send(f'{error_title} {ext}:**\n'
                           f'{type(e).__name__}: {e}')

@Meowth.command(name='unload')
@checks.is_owner()
async def _unload(ctx, *extensions):
    exts = [e for e in extensions if f"meowth.exts.{e}" in Meowth.extensions]
    for ext in exts:
        try:
            ctx.bot.unload_extension(f"meowth.exts.{ext}")
        except Exception as e:
            error_title = _('**Error when loading extension')
            await ctx.send(f'{error_title} {ext}:**\n'
                           f'{type(e).__name__}: {e}')
    s = 's' if len(exts) > 1 else ''
    if exts:
        await ctx.send(_("**Extension{plural} {est} unloaded.**\n").format(plural=s, est=', '.join(exts)))
    else:
        await ctx.send(_("**Extension{plural} {est} not loaded.**\n").format(plural=s, est=', '.join(exts)))

@Meowth.command(hidden=True, name="eval")
@checks.is_owner()
async def _eval(ctx, *, body: str):
    """Evaluates a code"""
    env = {
        'bot': ctx.bot,
        'ctx': ctx,
        'channel': ctx.channel,
        'author': ctx.author,
        'guild': ctx.guild,
        'message': ctx.message
    }
    def cleanup_code(content):
        """Automatically removes code blocks from the code."""
        # remove ```py\n```
        if content.startswith('```') and content.endswith('```'):
            return '\n'.join(content.split('\n')[1:-1])
        # remove `foo`
        return content.strip('` \n')
    env.update(globals())
    body = cleanup_code(body)
    stdout = io.StringIO()
    to_compile = (f'async def func():\n{textwrap.indent(body, "  ")}')
    try:
        exec(to_compile, env)
    except Exception as e:
        return await ctx.send(f'```py\n{e.__class__.__name__}: {e}\n```')
    func = env['func']
    try:
        with redirect_stdout(stdout):
            ret = await func()
    except Exception as e:
        value = stdout.getvalue()
        await ctx.send(f'```py\n{value}{traceback.format_exc()}\n```')
    else:
        value = stdout.getvalue()
        try:
            await ctx.message.add_reaction(config['command_done'])
        except:
            pass
        if ret is None:
            if value:
                paginator = commands.Paginator(prefix='```py')
                for line in textwrap.wrap(value, 80):
                    paginator.add_line(line.rstrip().replace('`', '\u200b`'))
                for p in paginator.pages:
                    await ctx.send(p)
        else:
            ctx.bot._last_result = ret
            await ctx.send(f'```py\n{value}{ret}\n```')

@Meowth.command()
@checks.is_owner()
async def save(ctx):
    """Save persistent state to file.

    Usage: !save
    File path is relative to current directory."""
    try:
        await _save()
        logger.info('CONFIG SAVED')
    except Exception as err:
        await _print(Meowth.owner, _('Error occured while trying to save!'))
        await _print(Meowth.owner, err)

async def _save():
    #human-readable format, used for backup only for now
    with tempfile.NamedTemporaryFile('w', dir=os.path.join('data'), delete=False, encoding="utf-8") as tf:
        tf.write(str(guild_dict))
        jstempname = tf.name
    try:
        os.remove(os.path.join('data', 'guilddict_backup.txt'))
    except OSError as e:
        pass
    try:
        os.rename(os.path.join('data', 'guilddict.txt'), os.path.join('data', 'guilddict_backup.txt'))
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise
    os.rename(jstempname, os.path.join('data', 'guilddict.txt'))
    #pickle, used for bot
    with tempfile.NamedTemporaryFile('wb', dir=os.path.dirname(os.path.join('data', 'serverdict')), delete=False) as tf:
        pickle.dump(guild_dict, tf, (- 1))
        tempname = tf.name
    try:
        os.remove(os.path.join('data', 'serverdict_backup'))
    except OSError as e:
        pass
    try:
        os.rename(os.path.join('data', 'serverdict'), os.path.join('data', 'serverdict_backup'))
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise
    os.rename(tempname, os.path.join('data', 'serverdict'))

Meowth.save = _save

@Meowth.command()
@checks.is_owner()
async def restart(ctx):
    """Restart after saving.

    Usage: !restart.
    Calls the save function and restarts Meowth."""
    try:
        await _save()
    except Exception as err:
        await _print(Meowth.owner, _('Error occured while trying to save!'))
        await _print(Meowth.owner, err)
    await ctx.channel.send(_('Restarting...'))
    Meowth._shutdown_mode = 26
    await Meowth.logout()

@Meowth.command()
@checks.is_owner()
async def exit(ctx):
    """Exit after saving.

    Usage: !exit.
    Calls the save function and quits the script."""
    try:
        await _save()
    except Exception as err:
        await _print(Meowth.owner, _('Error occured while trying to save!'))
        await _print(Meowth.owner, err)
    await ctx.channel.send(_('Shutting down...'))
    Meowth._shutdown_mode = 0
    await Meowth.logout()

"""
Server Management
"""

async def guild_cleanup(loop=True):
    while (not Meowth.is_closed()):
        guilddict_srvtemp = copy.deepcopy(guild_dict)
        logger.info('------ BEGIN ------')
        guilddict_srvtemp = guild_dict
        dict_guild_list = []
        bot_guild_list = []
        dict_guild_delete = []
        for guildid in guilddict_srvtemp.keys():
            dict_guild_list.append(guildid)
        for guild in Meowth.guilds:
            bot_guild_list.append(guild.id)
        guild_diff = set(dict_guild_list) - set(bot_guild_list)
        for s in guild_diff:
            dict_guild_delete.append(s)
        for s in dict_guild_delete:
            try:
                del guild_dict[s]
                logger.info(('Cleared ' + str(s)) +
                            ' from save data')
            except KeyError:
                pass
        logger.info('SAVING CHANGES')
        try:
            await _save()
        except Exception as err:
            logger.info('Server_Cleanup - SAVING FAILED' + err)
        logger.info('Server_Cleanup ------ END ------')
        await asyncio.sleep(7200)
        continue

async def _print(owner, message):
    if 'launcher' in sys.argv[1:]:
        if 'debug' not in sys.argv[1:]:
            await owner.send(message)
    print(message)
    logger.info(message)

async def maint_start():
    try:
        event_loop.create_task(guild_cleanup())
        logger.info('Maintenance Tasks Started')
    except KeyboardInterrupt as e:
        tasks.cancel()

event_loop = asyncio.get_event_loop()

"""
Events
"""
@Meowth.event
async def on_ready():
    Meowth.owner = discord.utils.get(
        Meowth.get_all_members(), id=config['master'])
    await _print(Meowth.owner, _('Starting up...'))
    Meowth.uptime = datetime.datetime.now()
    msg_success = 0
    msg_fail = 0
    guilds = len(Meowth.guilds)
    users = 0
    for guild in Meowth.guilds:
        users += guild.member_count
        if guild.id not in guild_dict:
            guild_dict[guild.id] = {
                'configure_dict':{
                    'welcome': {'enabled':False, 'welcomechan':'', 'welcomemsg':'default'},
                    'want': {'enabled':False, 'report_channels': []},
                    'raid': {'enabled':False, 'report_channels': {}, 'categories':'same', 'category_dict':{}},
                    'exraid': {'enabled':False, 'report_channels': {}, 'categories':'same', 'category_dict':{}, 'permissions':'everyone'},
                    'wild': {'enabled':False, 'report_channels': {}},
                    'meetup': {'enabled':False, 'report_channels': {}},
                    'tutorial': {'enabled':True, 'report_channels': {}},
                    'nest': {'enabled':False, 'report_channels': [], 'migration':datetime.datetime.now()},
                    'trade': {'enabled':False, 'report_channels': []},
                    'counters': {'enabled':False, 'auto_levels': []},
                    'research': {'enabled':False, 'report_channels': {}},
                    'archive': {'enabled':False, 'category':'same', 'list':None},
                    'invite': {'enabled':False},
                    'team':{'enabled':False, 'team_roles':{}},
                    'settings':{'offset':0, 'regional':None, 'done':False, 'prefix':Meowth.config['default_prefix'], 'config_sessions':{}},
                    'scanners':{'autoraid':False, 'raidlvls':[0], 'autoegg':False, 'egglvls':[0], 'autowild':False, 'wildfilter':[], 'autoquest':False, 'alarmaction':False}
                },
                'wildreport_dict:':{},
                'questreport_dict':{},
                'raidchannel_dict':{},
                'trainers':{},
                'trade_dict': {},
                'nest_dict': {}
            }
    await _print(Meowth.owner, _("Meowth! That's right!\n\n{server_count} servers connected.\n{member_count} members found.").format(server_count=guilds, member_count=users))
    await maint_start()

@Meowth.event
async def on_guild_join(guild):
    owner = guild.owner
    guild_dict[guild.id] = {
        'configure_dict':{
            'welcome': {'enabled':False, 'welcomechan':'', 'welcomemsg':'default'},
            'want': {'enabled':False, 'report_channels': []},
            'raid': {'enabled':False, 'report_channels': {}, 'categories':'same', 'category_dict':{}},
            'exraid': {'enabled':False, 'report_channels': {}, 'categories':'same', 'category_dict':{}, 'permissions':'everyone'},
            'wild': {'enabled':False, 'report_channels': {}},
            'meetup': {'enabled':False, 'report_channels': {}, 'categories':'same', 'catgory_dict':{}},
            'tutorial': {'enabled':True, 'report_channels': {}},
            'nest': {'enabled':False, 'report_channels': [], 'migration':datetime.datetime.now()},
            'trade': {'enabled':False, 'report_channels': []},
            'counters': {'enabled':False, 'auto_levels': []},
            'research': {'enabled':False, 'report_channels': {}},
            'archive': {'enabled':False, 'category':'same', 'list':None},
            'invite': {'enabled':False},
            'team':{'enabled':False, 'team_roles':{}},
            'settings':{'offset':0, 'regional':None, 'done':False, 'prefix':Meowth.config['default_prefix'], 'config_sessions':{}},
            'scanners':{'autoraid':False, 'raidlvls':[0], 'autoegg':False, 'egglvls':[0], 'autowild':False, 'wildfilter':[], 'autoquest':False, 'alarmaction':False}
        },
        'wildreport_dict:':{},
        'questreport_dict':{},
        'raidchannel_dict':{},
        'trainers':{},
        'trade_dict': {},
        'nest_dict': {}
    }
    await owner.send(_("Meowth! I'm Meowth, a Discord helper bot for Pokemon Go communities, and someone has invited me to your server! Type **!help** to see a list of things I can do, and type **!configure** in any channel of your server to begin!"))

@Meowth.event
async def on_guild_remove(guild):
    try:
        if guild.id in guild_dict:
            try:
                del guild_dict[guild.id]
            except KeyError:
                pass
    except KeyError:
        pass

@Meowth.event
async def on_member_join(member):
    'Welcome message to the server and some basic instructions.'
    guild = member.guild
    team_msg = _(' or ').join(['**!team {0}**'.format(team)
                           for team in config['team_dict'].keys()])
    if not guild_dict[guild.id]['configure_dict']['welcome']['enabled']:
        return
    # Build welcome message
    if guild_dict[guild.id]['configure_dict']['welcome'].get('welcomemsg', 'default') == "default":
        admin_message = _(' If you have any questions just ask an admin.')
        welcomemessage = _('Meowth! Welcome to {server}, {user}! ')
        if guild_dict[guild.id]['configure_dict']['team']['enabled']:
            welcomemessage += _('Set your team by typing {team_command}.').format(
                team_command=team_msg)
        welcomemessage += admin_message
    else:
        welcomemessage = guild_dict[guild.id]['configure_dict']['welcome']['welcomemsg']

    if guild_dict[guild.id]['configure_dict']['welcome']['welcomechan'] == 'dm':
        send_to = member
    elif str(guild_dict[guild.id]['configure_dict']['welcome']['welcomechan']).isdigit():
        send_to = discord.utils.get(guild.text_channels, id=int(guild_dict[guild.id]['configure_dict']['welcome']['welcomechan']))
    else:
        send_to = discord.utils.get(guild.text_channels, name=guild_dict[guild.id]['configure_dict']['welcome']['welcomechan'])
    if send_to:
        if welcomemessage.startswith("[") and welcomemessage.endswith("]"):
            await send_to.send(embed=discord.Embed(colour=guild.me.colour, description=welcomemessage[1:-1].format(server=guild.name, user=member.mention)))
        else:
            await send_to.send(welcomemessage.format(server=guild.name, user=member.mention))
    else:
        return

@Meowth.event
async def on_message(message):
    if "niandick" in message.content.lower():
        await message.add_reaction("\U0001F346")
    if (not message.author.bot):
        await Meowth.process_commands(message)

"""
Miscellaneous
"""

@Meowth.group(name='set', case_insensitive=True)
async def _set(ctx):
    """Changes a setting."""
    if ctx.invoked_subcommand == None:
        raise commands.BadArgument()
        return

@_set.command()
@commands.has_permissions(manage_guild=True)
async def regional(ctx, regional):
    """Changes server regional pokemon."""

    if regional.isdigit():
        regional = int(regional)
    else:
        regional = regional.lower()
        if regional == "reset" and checks.is_manager_check(ctx):
            msg = _("Are you sure you want to clear all regionals?")
            question = await ctx.channel.send(msg)
            try:
                timeout = False
                res, reactuser = await utils.ask(Meowth, question, ctx.message.author.id)
            except TypeError:
                timeout = True
            await utils.safe_delete(question)
            if timeout or res.emoji == config['answer_no']:
                return
            elif res.emoji == config['answer_yes']:
                pass
            else:
                return
            guild_dict_copy = copy.deepcopy(guild_dict)
            for guildid in guild_dict_copy.keys():
                guild_dict[guildid]['configure_dict']['settings']['regional'] = None
            return
        elif regional == 'clear':
            regional = None
            _set_regional(Meowth, ctx.guild, regional)
            await ctx.message.channel.send(_("Meowth! Regional raid boss cleared!"), delete_after=10)
            return
        else:
            regional = utils.get_number(Meowth, regional)
    if regional in Meowth.raid_list:
        _set_regional(Meowth, ctx.guild, regional)
        await ctx.message.channel.send(_("Meowth! Regional raid boss set to **{boss}**!").format(boss=utils.get_name(Meowth, regional).title()), delete_after=10)
    else:
        await ctx.message.channel.send(_("Meowth! That Pokemon doesn't appear in raids!"), delete_after=10)
        return

def _set_regional(bot, guild, regional):
    bot.guild_dict[guild.id]['configure_dict']['settings']['regional'] = regional

@_set.command()
@checks.guildchannel()
async def timezone(ctx, *, timezone: str = ''):
    """Changes server timezone."""
    if not ctx.author.guild_permissions.manage_guild:
        if not checks.is_manager_check(ctx):
            return
    try:
        timezone = float(timezone)
    except ValueError:
        await ctx.channel.send(_("I couldn't convert your answer to an appropriate timezone! Please double check what you sent me and resend a number from **-12** to **12**."), delete_after=10)
        return
    if (not ((- 12) <= timezone <= 14)):
        await ctx.channel.send(_("I couldn't convert your answer to an appropriate timezone! Please double check what you sent me and resend a number from **-12** to **12**."), delete_after=10)
        return
    _set_timezone(Meowth, ctx.guild, timezone)
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=guild_dict[ctx.channel.guild.id]['configure_dict']['settings']['offset'])
    await ctx.channel.send(_("Timezone has been set to: `UTC{offset}`\nThe current time is **{now}**").format(offset=timezone, now=now.strftime("%H:%M")), delete_after=10)

def _set_timezone(bot, guild, timezone):
    bot.guild_dict[guild.id]['configure_dict']['settings']['offset'] = timezone

@_set.command()
@checks.guildchannel()
@commands.has_permissions(manage_guild=True)
async def prefix(ctx, prefix=None):
    """Changes server prefix."""
    if prefix == 'clear':
        prefix = None
    prefix = prefix.strip()
    _set_prefix(Meowth, ctx.guild, prefix)
    if prefix != None:
        await ctx.channel.send(_('Prefix has been set to: `{}`').format(prefix))
    else:
        default_prefix = Meowth.config['default_prefix']
        await ctx.channel.send(_('Prefix has been reset to default: `{}`').format(default_prefix))

def _set_prefix(bot, guild, prefix):
    bot.guild_dict[guild.id]['configure_dict']['settings']['prefix'] = prefix

@_set.command()
@checks.guildchannel()
async def silph(ctx, silph_user: str = None):
    """Links a server member to a Silph Road Travelers Card."""
    if not silph_user:
        await ctx.send(_('Silph Road Travelers Card cleared!'), delete_after=10)
        try:
            del guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['silphid']
        except:
            pass
        return

    silph_cog = ctx.bot.cogs.get('Silph')
    if not silph_cog:
        return await ctx.send(
            _("The Silph Extension isn't accessible at the moment, sorry!"), delete_after=10)

    async with ctx.typing():
        card = await silph_cog.get_silph_card(silph_user)
        if not card:
            return await ctx.send(_('Silph Card for {silph_user} not found.').format(silph_user=silph_user), delete_after=10)

    if not card.discord_name:
        return await ctx.send(
            _('No Discord account found linked to this Travelers Card!'), delete_after=10)

    if card.discord_name != str(ctx.author):
        return await ctx.send(
            _('This Travelers Card is linked to another Discord account!'), delete_after=10)

    try:
        offset = ctx.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['offset']
    except KeyError:
        offset = None

    trainers = guild_dict[ctx.guild.id].get('trainers', {})
    author = trainers.get(ctx.author.id, {})
    author['silphid'] = silph_user
    trainers[ctx.author.id] = author
    guild_dict[ctx.guild.id]['trainers'] = trainers

    await ctx.send(
        _('This Travelers Card has been successfully linked to you!'),
        embed=card.embed(offset), delete_after=10)

@_set.command()
@checks.guildchannel()
async def pokebattler(ctx, pbid: int = 0):
    """Links a server member to a PokeBattler ID."""
    if not pbid:
        await ctx.send(_('Pokebattler ID cleared!'), delete_after=10)
        try:
            del guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['pokebattlerid']
        except:
            pass
        return
    trainers = guild_dict[ctx.guild.id].get('trainers', {})
    author = trainers.get(ctx.author.id, {})
    author['pokebattlerid'] = pbid
    trainers[ctx.author.id] = author
    guild_dict[ctx.guild.id]['trainers'] = trainers
    await ctx.send(_('Pokebattler ID set to {pbid}!').format(pbid=pbid), delete_after=10)

@_set.command()
@checks.guildchannel()
async def trainercode(ctx, *, trainercode: str = None):
    if not trainercode:
        await ctx.send(_('Trainer code cleared!'), delete_after=10)
        try:
            del guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['trainercode']
        except:
            pass
        return
    trainers = guild_dict[ctx.guild.id].get('trainers', {})
    author = trainers.get(ctx.author.id, {})
    author['trainercode'] = trainercode
    trainers[ctx.author.id] = author
    guild_dict[ctx.guild.id]['trainers'] = trainers
    await ctx.send(_(f'{ctx.author.display_name}\'s trainer code set to {trainercode}!'), delete_after=10)

@Meowth.group(name='get', case_insensitive=True)
@commands.has_permissions(manage_guild=True)
async def _get(ctx):
    """Get a setting value"""
    if ctx.invoked_subcommand == None:
        raise commands.BadArgument()
        return

@_get.command()
@commands.has_permissions(manage_guild=True)
async def prefix(ctx):
    """Get server prefix."""
    prefix = _get_prefix(Meowth, ctx.message)
    await ctx.channel.send(_('Prefix for this server is: `{}`').format(prefix), delete_after=10)

@_get.command()
@commands.has_permissions(manage_guild=True)
async def perms(ctx, channel_id = None):
    """Show Meowth's permissions for the guild and channel."""
    channel = discord.utils.get(ctx.bot.get_all_channels(), id=channel_id)
    guild = channel.guild if channel else ctx.guild
    channel = channel or ctx.channel
    guild_perms = guild.me.guild_permissions
    chan_perms = channel.permissions_for(guild.me)
    req_perms = discord.Permissions(268822608)

    embed = discord.Embed(colour=ctx.guild.me.colour)
    embed.set_author(name=_('Bot Permissions'), icon_url="https://i.imgur.com/wzryVaS.png")

    wrap = functools.partial(textwrap.wrap, width=20)
    names = [wrap(channel.name), wrap(guild.name)]
    if channel.category:
        names.append(wrap(channel.category.name))
    name_len = max(len(n) for n in names)
    def same_len(txt):
        return '\n'.join(txt + ([' '] * (name_len-len(txt))))
    names = [same_len(n) for n in names]
    chan_msg = [f"**{names[0]}** \n{channel.id} \n"]
    guild_msg = [f"**{names[1]}** \n{guild.id} \n"]
    def perms_result(perms):
        data = []
        meet_req = perms >= req_perms
        result = _("**PASS**") if meet_req else _("**FAIL**")
        data.append(f"{result} - {perms.value} \n")
        true_perms = [k for k, v in dict(perms).items() if v is True]
        false_perms = [k for k, v in dict(perms).items() if v is False]
        req_perms_list = [k for k, v in dict(req_perms).items() if v is True]
        true_perms_str = '\n'.join(true_perms)
        if not meet_req:
            missing = '\n'.join([p for p in false_perms if p in req_perms_list])
            meet_req_result = _("**MISSING**")
            data.append(f"{meet_req_result} \n{missing} \n")
        if true_perms_str:
            meet_req_result = _("**ENABLED**")
            data.append(f"{meet_req_result} \n{true_perms_str} \n")
        return '\n'.join(data)
    guild_msg.append(perms_result(guild_perms))
    chan_msg.append(perms_result(chan_perms))
    embed.add_field(name=_('GUILD'), value='\n'.join(guild_msg))
    if channel.category:
        cat_perms = channel.category.permissions_for(guild.me)
        cat_msg = [f"**{names[2]}** \n{channel.category.id} \n"]
        cat_msg.append(perms_result(cat_perms))
        embed.add_field(name=_('CATEGORY'), value='\n'.join(cat_msg))
    embed.add_field(name=_('CHANNEL'), value='\n'.join(chan_msg))

    try:
        await ctx.send(embed=embed)
    except discord.errors.Forbidden:
        # didn't have permissions to send a message with an embed
        try:
            msg = _("I couldn't send an embed here, so I've sent you a DM")
            await ctx.send(msg)
        except discord.errors.Forbidden:
            # didn't have permissions to send a message at all
            pass
        await ctx.author.send(embed=embed)

@Meowth.command(hidden=True)
async def template(ctx, *, sample_message):
    """Sample template messages to see how they would appear."""
    embed = None
    (msg, errors) = utils.do_template(sample_message, ctx.author, ctx.guild)
    if errors:
        if msg.startswith('[') and msg.endswith(']'):
            embed = discord.Embed(
                colour=ctx.guild.me.colour, description=msg[1:(- 1)])
            embed.add_field(name=_('Warning'), value=_('The following could not be found:\n{}').format(
                '\n'.join(errors)))
            await ctx.channel.send(embed=embed)
        else:
            msg = _('{}\n\n**Warning:**\nThe following could not be found: {}').format(
                msg, ', '.join(errors))
            await ctx.channel.send(msg)
    elif msg.startswith('[') and msg.endswith(']'):
        await ctx.channel.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=msg[1:(- 1)].format(user=ctx.author.mention)))
    else:
        await ctx.channel.send(msg.format(user=ctx.author.mention))

@Meowth.command()
@commands.has_permissions(manage_guild=True)
async def welcome(ctx, user: discord.Member=None):
    """Test welcome on yourself or mentioned member.

    Usage: !welcome [@member]"""
    if (not user):
        user = ctx.author
    await on_member_join(user)

@Meowth.command(hidden=True)
@commands.has_permissions(manage_guild=True)
async def outputlog(ctx):
    """Get current Meowth log.

    Usage: !outputlog
    Output is a link to hastebin."""
    with open(os.path.join('logs', 'meowth.log'), 'r', encoding='latin-1', errors='replace') as logfile:
        logdata = logfile.read()
    try:
        await ctx.channel.send(hastebin.post(logdata))
    except:
        await ctx.channel.send("Hastebin Error", delete_after=10)

@Meowth.command(aliases=['say'])
@commands.has_permissions(manage_guild=True)
async def announce(ctx, *, announce=None):
    """Repeats your message in an embed from Meowth.

    Usage: !announce [announcement]
    If the announcement isn't added at the same time as the command, Meowth will wait 3 minutes for a followup message containing the announcement."""
    message = ctx.message
    channel = message.channel
    guild = message.guild
    author = message.author
    if announce == None:
        announcewait = await channel.send(_("I'll wait for your announcement!"), delete_after=180)
        announcemsg = await Meowth.wait_for('message', timeout=180, check=(lambda reply: reply.author == message.author))
        if announcemsg != None:
            announce = announcemsg.content
            await utils.safe_delete(announcemsg)
        else:
            confirmation = await channel.send(_("Meowth! You took too long to send me your announcement! Retry when you're ready."), delete_after=10)
    embeddraft = discord.Embed(colour=guild.me.colour, description=announce)
    if ctx.invoked_with == "announce":
        title = _('Announcement')
        if Meowth.user.avatar_url:
            embeddraft.set_author(name=title, icon_url=Meowth.user.avatar_url)
        else:
            embeddraft.set_author(name=title)
    draft = await channel.send(embed=embeddraft)
    reaction_list = ['❔', config['answer_yes'], config['answer_no']]
    owner_msg_add = ''
    if checks.is_owner_check(ctx):
        owner_msg_add = '🌎 '
        owner_msg_add += _('to send it to all servers, ')
        reaction_list.insert(0, '🌎')

    def check(reaction, user):
        if user.id == author.id:
            if (str(reaction.emoji) in reaction_list) and (reaction.message.id == rusure.id):
                return True
        return False
    msg = _("That's what you sent, does it look good? React with ")
    msg += "{}❔ "
    msg += _("to send to another channel, ")
    msg += "{emoji} ".format(emoji=config['answer_yes'])
    msg += _("to send it to this channel, or ")
    msg += "{emoji} ".format(emoji=config['answer_no'])
    msg += _("to cancel")
    rusure = await channel.send(msg.format(owner_msg_add))
    try:
        timeout = False
        res, reactuser = await utils.ask(Meowth, rusure, author.id, react_list=reaction_list)
    except TypeError:
        timeout = True
    if not timeout:
        await utils.safe_delete(rusure)
        if res.emoji == config['answer_no']:
            confirmation = await channel.send(_('Announcement Cancelled.'), delete_after=10)
            await utils.safe_delete(draft)
        elif res.emoji == config['answer_yes']:
            confirmation = await channel.send(_('Announcement Sent.'), delete_after=10)
        elif res.emoji == '❔':
            channelwait = await channel.send(_('What channel would you like me to send it to?'))
            channelmsg = await Meowth.wait_for('message', timeout=60, check=(lambda reply: reply.author == message.author))
            if channelmsg.content.isdigit():
                sendchannel = Meowth.get_channel(int(channelmsg.content))
            elif channelmsg.raw_channel_mentions:
                sendchannel = Meowth.get_channel(channelmsg.raw_channel_mentions[0])
            else:
                sendchannel = discord.utils.get(guild.text_channels, name=channelmsg.content)
            if (channelmsg != None) and (sendchannel != None):
                announcement = await sendchannel.send(embed=embeddraft)
                confirmation = await channel.send(_('Announcement Sent.'), delete_after=10)
            elif sendchannel == None:
                confirmation = await channel.send(_("Meowth! That channel doesn't exist! Retry when you're ready."), delete_after=10)
            else:
                confirmation = await channel.send(_("Meowth! You took too long to send me your announcement! Retry when you're ready."), delete_after=10)
            await utils.safe_delete(channelwait)
            await utils.safe_delete(channelmsg)
            await utils.safe_delete(draft)
        elif (res.emoji == '🌎') and checks.is_owner_check(ctx):
            failed = 0
            sent = 0
            count = 0
            recipients = {

            }
            embeddraft.set_footer(text=_('For support, contact us on our Discord server. Invite Code: hhVjAN8'))
            embeddraft.colour = discord.Colour.lighter_grey()
            for guild in Meowth.guilds:
                recipients[guild.name] = guild.owner
            for (guild, destination) in recipients.items():
                try:
                    await destination.send(embed=embeddraft)
                except discord.HTTPException:
                    failed += 1
                    logger.info('Announcement Delivery Failure: {} - {}'.format(destination.name, guild))
                else:
                    sent += 1
                count += 1
            logger.info('Announcement sent to {} server owners: {} successful, {} failed.'.format(count, sent, failed))
            confirmation = await channel.send(_('Announcement sent to {} server owners: {} successful, {} failed.').format(count, sent, failed), delete_after=10)
    else:
        await utils.safe_delete(rusure)
        confirmation = await channel.send(_('Announcement Timed Out.'), delete_after=10)
    await asyncio.sleep(30)
    await utils.safe_delete(message)

@Meowth.command(name='uptime')
@checks.guildchannel()
async def cmd_uptime(ctx):
    "Shows Meowth's uptime"
    guild = ctx.guild
    channel = ctx.channel
    embed_colour = guild.me.colour or discord.Colour.lighter_grey()
    uptime_str = await _uptime(Meowth)
    embed = discord.Embed(colour=embed_colour, icon_url=Meowth.user.avatar_url)
    embed.add_field(name=_('Uptime'), value=uptime_str)
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        await channel.send(_('I need the `Embed links` permission to send this'))

async def _uptime(bot):
    'Shows info about Meowth'
    time_start = bot.uptime
    time_now = datetime.datetime.now()
    ut = relativedelta(time_now, time_start)
    (ut.years, ut.months, ut.days, ut.hours, ut.minutes)
    if ut.years >= 1:
        uptime = _('{yr}y {mth}m {day}d {hr}:{min}').format(yr=ut.years, mth=ut.months, day=ut.days, hr=ut.hours, min=ut.minutes)
    elif ut.months >= 1:
        uptime = _('{mth}m {day}d {hr}:{min}').format(mth=ut.months, day=ut.days, hr=ut.hours, min=ut.minutes)
    elif ut.days >= 1:
        uptime = _('{day} days {hr} hrs {min} mins').format(day=ut.days, hr=ut.hours, min=ut.minutes)
    elif ut.hours >= 1:
        uptime = _('{hr} hrs {min} mins {sec} secs').format(hr=ut.hours, min=ut.minutes, sec=ut.seconds)
    else:
        uptime = _('{min} mins {sec} secs').format(min=ut.minutes, sec=ut.seconds)
    return uptime

@Meowth.command()
@checks.guildchannel()
async def about(ctx):
    'Shows info about Meowth'
    huntr_repo = 'https://github.com/doonce/Meowth'
    huntr_name = 'BrenenP'
    guild_url = 'https://discord.gg/Qwb8xev'
    owner = Meowth.owner
    channel = ctx.channel
    uptime_str = await _uptime(Meowth)
    yourguild = ctx.guild.name
    yourmembers = len(ctx.guild.members)
    embed_colour = ctx.guild.me.colour or discord.Colour.lighter_grey()
    about = _("I'm Meowth! A Pokemon Go helper bot for Discord!\n\nHuntr integration was implemented by [{huntr_name}]({huntr_repo}).\n\n[Join our server]({server_invite}) if you have any questions or feedback.\n\n").format(huntr_name=huntr_name, huntr_repo=huntr_repo, server_invite=guild_url)
    member_count = 0
    guild_count = 0
    for guild in Meowth.guilds:
        guild_count += 1
        member_count += len(guild.members)
    embed = discord.Embed(colour=embed_colour, icon_url=Meowth.user.avatar_url)
    embed.add_field(name='About Meowth', value=about, inline=False)
    embed.add_field(name='Owner', value=owner)
    if guild_count > 1:
        embed.add_field(name='Servers', value=guild_count)
        embed.add_field(name='Members', value=member_count)
    embed.add_field(name='Your Server', value=yourguild)
    embed.add_field(name='Your Members', value=yourmembers)
    embed.add_field(name='Uptime', value=uptime_str)
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        await channel.send(_('I need the `Embed links` permission to send this'))

@Meowth.command()
@checks.allowteam()
async def team(ctx, *, team):
    """Set your team role.

    Usage: !team <team name>
    The team roles have to be created manually beforehand by the server administrator."""
    guild = ctx.guild
    toprole = guild.me.top_role.name
    position = guild.me.top_role.position
    guild_roles = guild_dict[guild.id]['configure_dict']['team']['team_roles']
    team_roles = {k: discord.utils.get(ctx.guild.roles, id=v) for (k, v) in guild_roles.items()}
    high_roles = []
    team_colors = [discord.Colour.blue(), discord.Colour.red(), discord.Colour.gold(), discord.Colour.default()]
    team_msg = _(' or ').join(['**!team {0}**'.format(team) for team in guild_roles.keys()])
    index = 0
    for teamrole in copy.deepcopy(guild_roles).keys():
        role = team_roles.get(teamrole, None)
        if not role:
            rolename = f"Meowth{teamrole.capitalize()}"
            try:
                role = await guild.create_role(name=rolename, hoist=False, mentionable=True, colour=team_colors[index])
            except discord.errors.HTTPException:
                await ctx.message.channel.send(_('Maximum guild roles reached.'), delete_after=10)
                return
            except (discord.errors.Forbidden, discord.errors.InvalidArgument):
                await ctx.message.channel.send(_('I can\'t create roles!.'), delete_after=10)
                return
            guild_dict[guild.id]['configure_dict']['team']['team_roles'][teamrole] = role.id
            team_roles[teamrole] = role
        if role.position > position:
            high_roles.append(role.name)
        index += 1
    if high_roles:
        await ctx.channel.send(_('Meowth! My roles are ranked lower than the following team roles: **{higher_roles_list}**\nPlease get an admin to move my roles above them!').format(higher_roles_list=', '.join(high_roles)), delete_after=10)
        return
    harmony = team_roles.get('harmony', None)
    team_split = team.lower().split()
    entered_team = team_split[0]
    entered_team = ''.join([i for i in entered_team if i.isalpha()])
    role = None
    if entered_team in team_roles.keys():
        role = team_roles[entered_team]
    else:
        await ctx.channel.send(_('Meowth! "{entered_team}" isn\'t a valid team! Try {available_teams}').format(entered_team=entered_team, available_teams=team_msg), delete_after=10)
        return
    for team in team_roles.values():
        if (team in ctx.author.roles) and (harmony not in ctx.author.roles):
            await ctx.channel.send(_('Meowth! You already have a team role!'), delete_after=10)
            return
    if role and (role.name.lower() == 'harmony') and (harmony in ctx.author.roles):
        await ctx.channel.send(_('Meowth! You are already in Team Harmony!'), delete_after=10)
    elif role == None:
        await ctx.channel.send(_('Meowth! The "{entered_team}" role isn\'t configured on this server! Contact an admin!').format(entered_team=entered_team), delete_after=10)
    else:
        try:
            if harmony and (harmony in ctx.author.roles):
                await ctx.author.remove_roles(harmony)
            await ctx.author.add_roles(role)
            await ctx.channel.send(_('Meowth! Added {member} to Team {team_name}! {team_emoji}').format(member=ctx.author.mention, team_name=entered_team.capitalize(), team_emoji=utils.parse_emoji(ctx.guild, config['team_dict'][entered_team])))
        except discord.Forbidden:
            await ctx.channel.send(_("Meowth! I can't add roles!"), delete_after=10)

@Meowth.command()
async def trainercode(ctx, user: discord.Member = None):
    """Displays a user's trainer code."""
    if not user:
        user = ctx.message.author
    trainercode = guild_dict[ctx.guild.id]['trainers'].setdefault(user.id, {}).get('trainercode', None)
    if trainercode:
        await ctx.channel.send(f"{user.display_name}\'s trainer code is: **{trainercode}**")
    else:
        await ctx.channel.send(f"{user.display_name} has not set a trainer code. Set it with **!set trainercode <code>**")

@Meowth.command()
async def profile(ctx, member: discord.Member = None):
    """Displays a member's social and reporting profile.

    Usage:!profile [member]"""
    if not member:
        member = ctx.message.author
    trainers = guild_dict[ctx.guild.id]['trainers']
    silph = guild_dict[ctx.guild.id]['trainers'].setdefault(member.id, {}).get('silphid', None)
    if silph:
        card = _("Traveler Card")
        silph = f"[{card}](https://sil.ph/{silph.lower()})"
    field_value = ""
    raids = trainers.setdefault(member.id, {}).get('raid_reports', 0)
    eggs = trainers.setdefault(member.id, {}).get('egg_reports', 0)
    exraids = trainers.setdefault(member.id, {}).get('ex_reports', 0)
    wilds = trainers.setdefault(member.id, {}).get('wild_reports', 0)
    research = trainers.setdefault(member.id, {}).get('research_reports', 0)
    nests = trainers.setdefault(member.id, {}).get('nest_reports', 0)
    wants = trainers.setdefault(member.id, {}).get('alerts', {}).get('wants', [])
    wants = sorted(wants)
    wants = [utils.get_name(Meowth, x).title() for x in wants]
    roles = [x.mention for x in sorted(member.roles, reverse=True) if ctx.guild.id != x.id]
    embed = discord.Embed(title=_("{member}\'s Trainer Profile").format(member=member.display_name), colour=member.colour)
    embed.set_thumbnail(url=member.avatar_url)
    embed.set_footer(text=f"User Registered: {member.created_at.strftime(_('%b %d, %Y %I:%M %p'))} | Status: {str(member.status).title()}")
    embed.add_field(name=_("Silph Road"), value=f"{silph}", inline=True)
    embed.add_field(name=_("Pokebattler"), value=f"{guild_dict[ctx.guild.id]['trainers'].setdefault(member.id, {}).get('pokebattlerid', None)}", inline=True)
    embed.add_field(name=_("Trainer Code"), value=f"{guild_dict[ctx.guild.id]['trainers'].setdefault(member.id, {}).get('trainercode', None)}", inline=True)
    embed.add_field(name=_("Member Since"), value=f"{member.joined_at.strftime(_('%b %d, %Y %I:%M %p'))}", inline=True)
    if guild_dict[ctx.guild.id]['configure_dict']['raid']['enabled']:
        field_value += _("Raid: **{raids}** | Egg: **{eggs}** | ").format(raids=raids, eggs=eggs)
    if guild_dict[ctx.guild.id]['configure_dict']['exraid']['enabled']:
        field_value += _("EX: **{exraids}** | ").format(exraids=exraids)
    if guild_dict[ctx.guild.id]['configure_dict']['wild']['enabled']:
        field_value += _("Wild: **{wilds}** | ").format(wilds=wilds)
    if guild_dict[ctx.guild.id]['configure_dict']['research']['enabled']:
        field_value += _("Research: **{research}** | ").format(research=research)
    if guild_dict[ctx.guild.id]['configure_dict']['nest']['enabled']:
        field_value += _("Nest: **{nest}** | ").format(nest=nests)
    embed.add_field(name=_("Reports"), value=field_value[:-3], inline=False)
    if guild_dict[ctx.guild.id]['configure_dict']['want']['enabled'] and wants:
        embed.add_field(name=_("Want List"), value=f"{(', ').join(wants)[:2000]}", inline=False)
    if roles:
        embed.add_field(name=_("Roles"), value=f"{(' ').join(roles)[:2000]}", inline=False)

    await ctx.send(embed=embed)

@Meowth.group(case_insensitive=True, invoke_without_command=True)
@checks.guildchannel()
async def leaderboard(ctx, type="total", range="1"):
    """Displays the top ten reporters of a server.

    Usage: !leaderboard [type] [page]
    Accepted types: raids, eggs, exraids, wilds, research, nest
    Page: 1 = 1 through 10, 2 = 11 through 20, etc."""
    trainers = copy.deepcopy(guild_dict[ctx.guild.id]['trainers'])
    leaderboard = []
    field_value = ""
    typelist = ["total", "raids", "exraids", "wilds", "research", "eggs", "nests"]
    type = type.lower()
    if type.isdigit():
        range = type
        type = "total"
    if not range.isdigit():
        range = "1"
    range = int(range) * 10
    begin_range = int(range) - 10
    rank = int(range) - 9
    if type not in typelist:
        await ctx.send(_("Leaderboard type not supported. Please select from: **{typelist}**").format(typelist = ", ".join(typelist)), delete_after=10)
        return
    for trainer in trainers.keys():
        user = ctx.guild.get_member(trainer)
        raids = trainers[trainer].setdefault('raid_reports', 0)
        wilds = trainers[trainer].setdefault('wild_reports', 0)
        exraids = trainers[trainer].setdefault('ex_reports', 0)
        eggs = trainers[trainer].setdefault('egg_reports', 0)
        research = trainers[trainer].setdefault('research_reports', 0)
        nests = trainers[trainer].setdefault('nest_reports', 0)
        total_reports = raids + wilds + exraids + eggs + research
        trainer_stats = {'trainer':trainer, 'total':total_reports, 'raids':raids, 'wilds':wilds, 'research':research, 'exraids':exraids, 'eggs':eggs, 'nests':nests}
        if trainer_stats[type] > 0 and user:
            leaderboard.append(trainer_stats)
    leaderboard = sorted(leaderboard, key= lambda x: x[type], reverse=True)[begin_range:int(range)]
    embed = discord.Embed(colour=ctx.guild.me.colour)
    embed.set_author(name=_("Reporting Leaderboard ({type})").format(type=type.title()), icon_url=Meowth.user.avatar_url)
    for trainer in leaderboard:
        user = ctx.guild.get_member(trainer['trainer'])
        if user:
            if guild_dict[ctx.guild.id]['configure_dict']['raid']['enabled']:
                field_value += _("Raid: **{raids}** | Egg: **{eggs}** | ").format(raids=trainer['raids'], eggs=trainer['eggs'])
            if guild_dict[ctx.guild.id]['configure_dict']['exraid']['enabled']:
                field_value += _("EX: **{exraids}** | ").format(exraids=trainer['exraids'])
            if guild_dict[ctx.guild.id]['configure_dict']['wild']['enabled']:
                field_value += _("Wild: **{wilds}** | ").format(wilds=trainer['wilds'])
            if guild_dict[ctx.guild.id]['configure_dict']['research']['enabled']:
                field_value += _("Research: **{research}** | ").format(research=trainer['research'])
            if guild_dict[ctx.guild.id]['configure_dict']['nest']['enabled']:
                field_value += _("Nest: **{nest}** | ").format(nest=trainer['nests'])
            embed.add_field(name=f"{rank}. {user.display_name} - {type.title()}: **{trainer[type]}**", value=field_value[:-3], inline=False)
            field_value = ""
            rank += 1
    if len(embed.fields) == 0:
        embed.add_field(name=_("No Reports"), value=_("Nobody has made a report or this report type is disabled."))
    await ctx.send(embed=embed)

@leaderboard.command(name='reset')
@commands.has_permissions(manage_guild=True)
async def reset(ctx, *, user=None, type=None):
    guild = ctx.guild
    trainers = guild_dict[guild.id]['trainers']
    tgt_string = ""
    tgt_trainer = None
    if user:
        converter = commands.MemberConverter()
        for argument in user.split():
            try:
                tgt_trainer = await converter.convert(ctx, argument)
                tgt_string = tgt_trainer.display_name
            except:
                tgt_trainer = None
                tgt_string = _("every user")
            if tgt_trainer:
                user = user.replace(argument, "").strip()
                break
        for argument in user.split():
            if "raid" in argument.lower():
                type = "raid_reports"
                break
            elif "egg" in argument.lower():
                type = "egg_reports"
                break
            elif "ex" in argument.lower():
                type = "ex_reports"
                break
            elif "wild" in argument.lower():
                type = "wild_reports"
                break
            elif "res" in argument.lower():
                type = "research_reports"
                break
            elif "nest" in argument.lower():
                type = "nest_reports"
                break
    if not type:
        type = "total_reports"
    if not tgt_string:
        tgt_string = _("every user")
    msg = _("Are you sure you want to reset the **{type}** report stats for **{target}**?").format(type=type.replace("_", " ").title(), target=tgt_string)
    question = await ctx.channel.send(msg)
    try:
        timeout = False
        res, reactuser = await utils.ask(Meowth, question, ctx.message.author.id)
    except TypeError:
        timeout = True
    await utils.safe_delete(question)
    if timeout or res.emoji == config['answer_no']:
        return
    elif res.emoji == config['answer_yes']:
        pass
    else:
        return
    for trainer in trainers:
        if tgt_trainer:
            trainer = tgt_trainer.id
        if type == "total_reports":
            trainers[trainer]['raid_reports'] = 0
            trainers[trainer]['wild_reports'] = 0
            trainers[trainer]['ex_reports'] = 0
            trainers[trainer]['egg_reports'] = 0
            trainers[trainer]['research_reports'] = 0
            trainers[trainer]['nest_reports'] = 0
        else:
            trainers[trainer][type] = 0
        if tgt_trainer:
            await ctx.send(_("{trainer}'s report stats have been cleared!").format(trainer=tgt_trainer.display_name), delete_after=10)
            return
    await ctx.send("This server's report stats have been reset!", delete_after=10)


try:
    event_loop.run_until_complete(Meowth.start(config['bot_token']))
except discord.LoginFailure:
    logger.critical('Invalid token')
    event_loop.run_until_complete(Meowth.logout())
    Meowth._shutdown_mode = 0
except KeyboardInterrupt:
    logger.info('Keyboard interrupt detected. Quitting...')
    event_loop.run_until_complete(Meowth.logout())
    Meowth._shutdown_mode = 0
except Exception as e:
    logger.critical('Fatal exception', exc_info=e)
    event_loop.run_until_complete(Meowth.logout())
finally:
    pass
sys.exit(Meowth._shutdown_mode)
