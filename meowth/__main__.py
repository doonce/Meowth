
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

from contextlib import redirect_stdout
from time import strftime

import discord
from discord.ext import commands

from meowth import checks
from meowth.bot import MeowthBot
from meowth.errors import custom_error_handling
from meowth.logs import init_loggers
from meowth.exts import pokemon as pkmn_class
from meowth.exts import utilities as utils

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
    Meowth.config = config
    pkmn_class.Pokemon.generate_lists(Meowth)
    Meowth.raid_list = utils.get_raidlist(Meowth)
    Meowth.pkmn_info_path = pokemon_path_source
    Meowth.raid_json_path = raid_path_source

load_config()

Meowth.load_config = load_config

event_loop = asyncio.get_event_loop()

required_exts = ['utilities', 'pokemon', 'configure']
optional_exts = ['want', 'wild', 'raid', 'list', 'gymmatching', 'tutorial', 'silph', 'trade', 'research', 'nest', 'huntr', 'trainers']
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
    await Meowth.wait_until_ready()
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
        if not loop:
            return
        await asyncio.sleep(7200)
        continue

async def _print(owner, message):
    if 'launcher' in sys.argv[1:] and owner:
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

"""
Events
"""
@Meowth.event
async def on_connect():
    Meowth.owner = None
    await _print(Meowth.owner, _('Connected to Discord...'))
    Meowth.uptime = datetime.datetime.now()

@Meowth.event
async def on_ready():
    Meowth.owner = discord.utils.get(
        Meowth.get_all_members(), id=config['master'])
    await _print(Meowth.owner, _('Starting up...'))
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
                'wildreport_dict':{},
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

@Meowth.command()
@commands.has_permissions(manage_guild=True)
async def welcome(ctx, user: discord.Member=None):
    """Test welcome on yourself or mentioned member.

    Usage: !welcome [@member]"""
    if (not user):
        user = ctx.author
    await on_member_join(user)

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
