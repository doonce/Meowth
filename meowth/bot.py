
import asyncio
import copy
import gettext
import io
import json
import pickle
import tempfile
import textwrap
import time
import traceback
import discord
import datetime
import sys
import os
import pkg_resources
import platform
import logging
import aiohttp
import itertools

from discord.ext import commands
from contextlib import redirect_stdout
from time import strftime
from dateutil.relativedelta import relativedelta
from meowth import checks, errors, config
from meowth.exts import utilities as utils
from meowth.exts import pokemon as pkmn_class
from meowth.context import Context

class MeowthBot(commands.AutoShardedBot):
    """Custom Discord Bot class for Meowth"""

    def __init__(self, **kwargs):
        self.default_prefix = config.default_prefix
        self.owner = config.master
        self.launch_time = None
        self.language = config.bot_language
        self.pkmn_language = config.pokemon_language
        self.core_dir = os.path.dirname(os.path.realpath(__file__))
        self.bot_dir = os.path.dirname(self.core_dir)
        self.data_dir = os.path.join(self.bot_dir, "data")
        self.ext_dir = os.path.join(self.bot_dir, "exts")
        self.pkmn_info_path = os.path.join('locale', '{0}', 'pkmn.json').format(self.pkmn_language)
        self.raid_json_path = os.path.join('data', 'raid_info.json')
        self.config = config
        self.token = config.bot_token
        self.co_owners = config.bot_coowners
        self.managers = config.managers
        self.custom_emoji = config.custom_emoji
        kwargs = dict(owner_id=self.owner,
                      status=discord.Status.dnd, case_insensitive=True,
                      **kwargs)
        super().__init__(**kwargs)
        self.logger = logging.getLogger('meowth')
        self.report_dicts = ['wildreport_dict:', 'questreport_dict', 'pokealarm_dict', 'trade_dict', 'nest_dict', 'wildreport_dict', 'lure_dict', 'pvp_dict', 'invasion_dict', 'pokehuntr_dict']
        self.channel_report_dicts = ['raidchannel_dict', 'exraidchannel_dict', 'meetup_dict', 'raidtrain_dict']
        self.type_list = ["normal", "fighting", "flying", "poison", "ground", "rock", "bug", "ghost", "steel", "fire", "water", "grass", "electric", "psychic", "ice", "dragon", "dark", "fairy"]
        self.item_list = ["incense", "poke ball", "great ball", "ultra ball", "master ball", "potion", "super potion", "hyper potion", "max potion", "revive", "max revive", "razz berry", "golden razz berry", "nanab berry", "pinap berry", "silver pinap berry", "fast tm", "charged tm", "rare candy", "lucky egg", "stardust", "lure module", "glacial lure module", "magnetic lure module", "mossy lure module", "star piece", "premium raid pass", "egg incubator", "super incubator", "team medallion", "sun stone", "metal coat", "dragon scale", "up-grade", "sinnoh stone", "unova stone", "mysterious component", "rocket radar"]

    @property
    def avatar(self):
        return self.user.avatar_url_as(static_format='png')

    @property
    def avatar_small(self):
        return self.user.avatar_url_as(static_format='png', size=64)

    @property
    def uptime(self):
        return relativedelta(datetime.datetime.utcnow(), self.launch_time)

    @property
    def uptime_str(self):
        uptime = self.uptime
        year_str, month_str, day_str, hour_str = ('',)*4
        if uptime.years >= 1:
            year_str = "{0}y ".format(uptime.years)
        if uptime.months >= 1 or year_str:
            month_str = "{0}m ".format(uptime.months)
        if uptime.days >= 1 or month_str:
            d_unit = 'd' if month_str else ' days'
            day_str = "{0}{1} ".format(uptime.days, d_unit)
        if uptime.hours >= 1 or day_str:
            h_unit = ':' if month_str else ' hrs'
            hour_str = "{0}{1}".format(uptime.hours, h_unit)
        m_unit = '' if month_str else ' mins'
        mins = uptime.minutes if month_str else ' {0}'.format(uptime.minutes)
        secs = '' if day_str else ' {0} secs'.format(uptime.seconds)
        min_str = "{0}{1}{2}".format(mins, m_unit, secs)

        uptime_str = ''.join((year_str, month_str, day_str, hour_str, min_str))

        return uptime_str

    @property
    def version(self):
        return pkg_resources.get_distribution("meowth").version

    @property
    def py_version(self):
        return platform.python_version()

    @property
    def dpy_version(self):
        return pkg_resources.get_distribution("discord.py").version

    @property
    def platform(self):
        return platform.platform()

    @property
    def raid_info(self):
        with open(self.raid_json_path, 'r') as fd:
            return json.load(fd)

    @property
    def pkmn_info(self):
        with open(self.pkmn_info_path, 'r', encoding="utf8") as fd:
            return json.load(fd)

    @property
    def type_chart(self):
        with open(os.path.join('data', 'type_chart.json'), 'r') as fd:
            return json.load(fd)

    @property
    def pkmn_list(self):
        pkmn_list = []
        count = 1
        for k, v in self.pkmn_info.items():
            if v['number'] == count:
                pkmn_list.append(k)
            count += 1
        return pkmn_list

    @property
    async def save(self):
        #human-readable format, used for backup only for now
        with tempfile.NamedTemporaryFile('w', dir=os.path.join('data'), delete=False, encoding="utf-8") as tf:
            tf.write(str(self.guild_dict))
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
            pickle.dump(self.guild_dict, tf, (- 1))
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

    async def on_connect(self):
        print('Connected to Discord...')
        self.launch_time = datetime.datetime.utcnow()
        await self.change_presence(status=discord.Status.idle)
        await pkmn_class.Pokemon.generate_lists(self)
        self.raid_dict = await utils.get_raid_dict(self)
        self.raid_list = list(itertools.chain.from_iterable(self.raid_dict.values()))

    async def on_ready(self):
        print(_('Starting up...'))
        await self.change_presence(status=discord.Status.online, activity=discord.Game(name="Pokemon Go"))
        msg_success = 0
        msg_fail = 0
        guilds = len(self.guilds)
        users = 0
        for guild in list(self.guilds):
            # RUN ONCE
            try:
                test_var = self.guild_dict[guild.id]['configure_dict']['train']['report_channels']
            except KeyError:
                self.guild_dict[guild.id]['configure_dict']['train'] = copy.deepcopy(self.guild_dict[guild.id]['configure_dict']['meetup'])
            while True:
                try:
                    test_var = self.guild_dict[guild.id]['configure_dict']['scanners']['reports']['raid']
                    break
                except KeyError:
                    pass
                report_dict = {}
                try:
                    test_Var = self.guild_dict[guild.id]['configure_dict']['scanners']['autoraid']
                except KeyError:
                    break
                auto_raid = self.guild_dict[guild.id]['configure_dict']['scanners']['autoraid']
                auto_egg = self.guild_dict[guild.id]['configure_dict']['scanners']['autoegg']
                auto_wild = self.guild_dict[guild.id]['configure_dict']['scanners']['autowild']
                auto_quest = self.guild_dict[guild.id]['configure_dict']['scanners']['autoquest']
                auto_inv = self.guild_dict[guild.id]['configure_dict']['scanners']['autoquest']
                auto_lure = self.guild_dict[guild.id]['configure_dict']['scanners']['autoquest']
                report_dict = {"raid":auto_raid, "egg":auto_egg, "wild":auto_wild, "research":auto_quest, "invasion":auto_quest, "lure":auto_lure}
                self.guild_dict[guild.id]['configure_dict']['scanners']['reports'] = report_dict
                for item in ["autoraid", "autoegg", "autowild", "autoquest"]:
                    try:
                        del self.guild_dict[guild.id]['configure_dict']['scanners'][item]
                    except KeyError:
                        continue
                break
            type_list = ["raid", "egg", "ex", "wild", "research", "nest", "lure", "invasion", "trade", "pvp"]
            for trainer in self.guild_dict[guild.id]['trainers']:
                try:
                    if isinstance(self.guild_dict[guild.id]['trainers'][trainer]['alerts']['settings']['categories'], list):
                        del self.guild_dict[guild.id]['trainers'][trainer]['alerts']['settings']['categories']
                except KeyError:
                    pass
                try:
                    test_var = self.guild_dict[guild.id]['trainers'][trainer]['reports']
                    break
                except KeyError:
                    pass
                for item in type_list:
                    item_name = f"{item}_reports"
                    item_reports =  self.guild_dict[guild.id]['trainers'][trainer].get(item_name, 0)
                    if item_reports:
                        test_var = self.guild_dict[guild.id]['trainers'][trainer].setdefault('reports', {})
                        self.guild_dict[guild.id]['trainers'][trainer]['reports'][item] = item_reports
                        del self.guild_dict[guild.id]['trainers'][trainer][item_name]
            # /Run Once
            try:
                users += guild.member_count
                if guild.id not in self.guild_dict:
                    self.guild_dict[guild.id] = {
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
                            'settings':{'offset':0, 'regional':None, 'done':False, 'prefix':self.default_prefix, 'config_sessions':{}},
                            'scanners':{'reports':{'raid':False, 'egg':False, 'wild':False, 'research':False, 'invasion':False, 'lure':False}, 'raidlvls':[0], 'egglvls':[0], 'wildfilter':[], 'alarmaction':False}
                        },
                        'wildreport_dict':{},
                        'questreport_dict':{},
                        'raidchannel_dict':{},
                        'trainers':{},
                        'trade_dict': {},
                        'nest_dict': {}
                    }
            except AttributeError:
                continue
        print("Meowth! That's right!\n\n{server_count} servers connected.\n{member_count} members found.".format(server_count=guilds, member_count=users))

    async def on_guild_join(guild):
        owner = guild.owner
        self.guild_dict[guild.id] = {
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
                'settings':{'offset':0, 'regional':None, 'done':False, 'prefix':self.default_prefix, 'config_sessions':{}},
                'scanners':{'reports':{'raid':False, 'egg':False, 'wild':False, 'research':False, 'invasion':False, 'lure':False}, 'raidlvls':[0], 'egglvls':[0], 'wildfilter':[], 'alarmaction':False}
            },
            'wildreport_dict:':{},
            'questreport_dict':{},
            'raidchannel_dict':{},
            'trainers':{},
            'trade_dict': {},
            'nest_dict': {}
        }
        await owner.send(_("Meowth! I'm Meowth, a Discord helper bot for Pokemon Go communities, and someone has invited me to your server! Type **!help** to see a list of things I can do, and type **!configure** in any channel of your server to begin!"))

    async def on_guild_remove(self, guild):
        try:
            if guild.id in self.guild_dict:
                try:
                    del self.guild_dict[guild.id]
                except KeyError:
                    pass
        except KeyError:
            pass

    async def on_member_join(self, member):
        'Welcome message to the server and some basic instructions.'
        guild = member.guild
        team_msg = _(' or ').join(['**!team {0}**'.format(team)
                               for team in config.team_dict.keys()])
        if not self.guild_dict[guild.id]['configure_dict']['welcome']['enabled']:
            return
        # Build welcome message
        if self.guild_dict[guild.id]['configure_dict']['welcome'].get('welcomemsg', 'default') == "default":
            admin_message = _(' If you have any questions just ask an admin.')
            welcomemessage = _('Meowth! Welcome to {server}, {user}! ')
            if self.guild_dict[guild.id]['configure_dict']['team']['enabled']:
                welcomemessage += _('Set your team by typing {team_command}.').format(
                    team_command=team_msg)
            welcomemessage += admin_message
        else:
            welcomemessage = self.guild_dict[guild.id]['configure_dict']['welcome']['welcomemsg']

        if self.guild_dict[guild.id]['configure_dict']['welcome']['welcomechan'] == 'dm':
            send_to = member
        elif str(self.guild_dict[guild.id]['configure_dict']['welcome']['welcomechan']).isdigit():
            send_to = discord.utils.get(guild.text_channels, id=int(self.guild_dict[guild.id]['configure_dict']['welcome']['welcomechan']))
        else:
            send_to = discord.utils.get(guild.text_channels, name=self.guild_dict[guild.id]['configure_dict']['welcome']['welcomechan'])
        if send_to:
            if welcomemessage.startswith("[") and welcomemessage.endswith("]"):
                await send_to.send(embed=discord.Embed(colour=guild.me.colour, description=welcomemessage[1:-1].format(server=guild.name, user=member.mention)))
            else:
                await send_to.send(welcomemessage.format(server=guild.name, user=member.mention))
        else:
            return

    async def on_message(self, message):
        if (not message.author.bot):
            await self.process_commands(message)

    async def on_raw_reaction_add(self, payload):
        emoji = payload.emoji.name
        try:
            user = self.get_user(payload.user_id)
        except AttributeError:
            return
        if user == self.user:
            return
        if config.custom_emoji.get('delete_dm', '\U0001f5d1') in emoji:
            channel = user.dm_channel
            if not channel:
                channel = await user.create_dm()
            if not channel:
                return
            try:
                message = await channel.fetch_message(payload.message_id)
                if message.author.id == self.user.id:
                    await message.delete()
            except (discord.errors.NotFound, AttributeError, discord.Forbidden):
                return
        elif u'\U0001F4A8' in emoji:
            channel = self.get_channel(payload.channel_id)
            guild = getattr(channel, "guild", None)
            if guild:
                user = guild.get_member(payload.user_id)
            else:
                return
            can_manage = channel.permissions_for(user).manage_messages
            if not can_manage:
                return
            try:
                message = await channel.fetch_message(payload.message_id)
            except (discord.errors.NotFound, AttributeError, discord.Forbidden):
                return
            if message.author != self.user:
                return
            in_reports = False
            for report_dict in self.report_dicts:
                if message.id in self.guild_dict[guild.id].get(report_dict, {}):
                    in_reports = True
                    break
            if not in_reports:
                await utils.safe_delete(message)

    async def process_commands(self, message):
        """Processes commands that are registed with the bot and it's groups.

        Without this being run in the main `on_message` event, commands will
        not be processed.
        """
        if message.author.bot:
            return
        ctx = await self.get_context(message, cls=Context)
        for report_dict in ctx.bot.channel_report_dicts:
            if ctx.guild and ctx.channel.id in ctx.bot.guild_dict[ctx.guild.id].setdefault(report_dict, {}):
                if ctx.bot.guild_dict[ctx.guild.id]['configure_dict']['invite']['enabled']:
                    raid_type = ctx.bot.guild_dict[ctx.guild.id][report_dict].get(ctx.channel.id, {}).get('type', None)
                    raid_level = ctx.bot.guild_dict[ctx.guild.id][report_dict].get(ctx.channel.id, {}).get('egg_level', None)
                    meetup = ctx.bot.guild_dict[ctx.guild.id][report_dict].get(ctx.channel.id, {}).get('meetup', {})
                    if (raid_type == "exraid" or raid_level == "EX") and not meetup:
                        if ctx.author not in ctx.channel.overwrites:
                            if not ctx.channel.permissions_for(ctx.author).manage_guild and not ctx.channel.permissions_for(ctx.author).manage_channels and not ctx.channel.permissions_for(ctx.author).manage_messages:
                                ow = ctx.channel.overwrites_for(ctx.author)
                                ow.send_messages = False
                                try:
                                    await ctx.channel.set_permissions(ctx.author, overwrite = ow)
                                except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.InvalidArgument):
                                    pass
                                await utils.safe_delete(ctx.message)
                                await ctx.bot.on_command_error(ctx, errors.EXInviteFail())
                                return
        if not ctx.command:
            return
        await self.invoke(ctx)
