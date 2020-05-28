import asyncio
import copy
import re
import time
import datetime
import dateparser
import textwrap
import logging
import aiohttp
import os
import json
import itertools
import traceback
import functools
from dateutil.relativedelta import relativedelta
from urllib import parse

import discord
from discord.ext import commands, tasks

from meowth import checks, errors
from meowth.exts import pokemon as pkmn_class
from meowth.exts import utilities as utils

logger = logging.getLogger("meowth")

class Raid(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.channel_cleanup.start()
        self.lobby_cleanup.start()
        self.auto_raid_json.start()
        self.bot.active_channels = {}

    def cog_unload(self):
        for task in asyncio.Task.all_tasks():
            if "expiry_check" in str(task) and "raid" in str(task):
                task.cancel()
        self.channel_cleanup.cancel()
        self.lobby_cleanup.cancel()
        self.auto_raid_json.cancel()

    """
    Event Handlers
    """

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        channel = self.bot.get_channel(payload.channel_id)
        guild = getattr(channel, "guild", None)
        if guild and guild.id not in list(self.bot.guild_dict.keys()):
            return
        try:
            user = self.bot.get_user(payload.user_id)
        except AttributeError:
            return
        if user == self.bot.user:
            return
        if guild:
            user = guild.get_member(payload.user_id)
        else:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.errors.NotFound, AttributeError, discord.Forbidden):
            return
        ctx = await self.bot.get_context(message)
        react_message = None
        for report_dict in self.bot.channel_report_dicts:
            for report_channel in self.bot.guild_dict[guild.id][report_dict]:
                if message.id == self.bot.guild_dict[guild.id][report_dict][report_channel].get('raid_report'):
                    await utils.remove_reaction(message, payload.emoji, user)
                    channel = guild.get_channel(report_channel)
                    ctx.message.author, ctx.author = user, user
                    ctx.message.channel, ctx.channel = channel, channel
                    react_message = "raid_report"
                    break
                elif message.id == self.bot.guild_dict[guild.id][report_dict][report_channel].get('raid_message'):
                    await utils.remove_reaction(message, payload.emoji, user)
                    ctx.message.author, ctx.author = user, user
                    react_message = "raid_message"
                    break
                elif message.id == self.bot.guild_dict[guild.id][report_dict][report_channel].get('ctrsmessage'):
                    await utils.remove_reaction(message, payload.emoji, user)
                    react_message = "ctrsmessage"
                    break
                elif message.id in self.bot.guild_dict[guild.id][report_dict][report_channel].get('next_trains', {}):
                    await utils.remove_reaction(message, payload.emoji, user)
                    react_message = "next_trains"
                    break
                elif channel.id == report_channel:
                    ctx.message.author, ctx.author = user, user
                    react_message = "report_channel"
                    break
            if react_message:
                break
        if not react_message:
            return
        report_dict = await utils.get_report_dict(self.bot, channel)
        def get_teamcounts(raid_channel, trainer, lobby):
            total = lobby[trainer]['count']
            mystic = lobby[trainer]['party']['mystic']
            valor = lobby[trainer]['party']['valor']
            instinct = lobby[trainer]['party']['instinct']
            unknown = lobby[trainer]['party']['unknown']
            return f"{total} {mystic}m {valor}v {instinct}i {unknown}u"
        if react_message == "ctrsmessage":
            ctrs_dict = self.bot.guild_dict[guild.id].get(report_dict, {})[channel.id]['ctrs_dict']
            for i in ctrs_dict:
                if ctrs_dict[i]['emoji'] == str(payload.emoji):
                    newembed = ctrs_dict[i]['embed']
                    moveset = i
                    break
            else:
                return
            await message.edit(embed=newembed)
            self.bot.guild_dict[guild.id].get(report_dict, {})[channel.id]['moveset'] = moveset
        elif str(payload.emoji) == self.bot.custom_emoji.get('raid_report', u'\U0001F4E2') or str(payload.emoji) == self.bot.custom_emoji.get('meetup_report', u'\U0001F4E2'):
            ctx.author, ctx.message.author = user, user
            channel = self.bot.get_channel(payload.channel_id)
            ctx.message.channel, ctx.channel = channel, channel
            ctx.message.content = ""
            if report_dict == "raidtrain_dict":
                return await ctx.invoke(self.bot.get_command('train'))
            elif report_dict == "meetup_dict":
                return await ctx.invoke(self.bot.get_command('meetup'))
            else:
                if self.bot.guild_dict[guild.id][report_dict][report_channel]['type'] == "exraid" or self.bot.guild_dict[guild.id][report_dict][report_channel]['egg_level'] == "EX":
                    return await ctx.invoke(self.bot.get_command('exraid'))
                else:
                    return await ctx.invoke(self.bot.get_command('raid'))
        elif react_message == "raid_report" or react_message == "raid_message" or react_message == "report_channel":
            if str(payload.emoji) == self.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f'):
                channel = self.bot.get_channel(payload.channel_id)
                ctx.message.channel, ctx.channel = channel, channel
                await asyncio.sleep(0.25)
                await utils.remove_reaction(message, payload.emoji, self.bot.user)
                await asyncio.sleep(0.25)
                await utils.remove_reaction(message, payload.emoji, user)
                ctx.message.content = ""
                await ctx.invoke(self.bot.get_command("list"))
                await asyncio.sleep(5)
                return await utils.add_reaction(message, payload.emoji)
            teamcounts = "1"
            if channel.id in self.bot.guild_dict[guild.id][report_dict]:
                if self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('invite', {}).get('enabled', False):
                    if self.bot.guild_dict[guild.id][report_dict][channel.id]['egg_level'] == "EX" or self.bot.guild_dict[guild.id][report_dict][channel.id]['type'] == "exraid":
                        if user not in channel.overwrites:
                            if not channel.permissions_for(user).manage_guild and not channel.permissions_for(user).manage_channels and not channel.permissions_for(user).manage_messages:
                                return
            if user.id in self.bot.guild_dict[guild.id][report_dict][channel.id]['trainer_dict']:
                teamcounts = get_teamcounts(channel, user.id, self.bot.guild_dict[guild.id][report_dict][channel.id]['trainer_dict'])
            if str(payload.emoji) == self.bot.custom_emoji.get('raid_info', u'\U00002139\U0000fe0f') and react_message == "raid_message":
                prefix = self.bot.guild_dict[guild.id]['configure_dict'].setdefault('settings', {}).setdefault('prefix', None)
                prefix = prefix or self.bot.default_prefix
                avatar = self.bot.user.avatar_url
                if report_dict == "raidtrain_dict":
                    await utils.get_train_help(prefix, avatar, user)
                else:
                    await utils.get_raid_help(prefix, avatar, user)
            elif str(payload.emoji) == self.bot.custom_emoji.get('raid_maybe', u'\U00002753'):
                await self._rsvp(ctx, "maybe", teamcounts)
            elif str(payload.emoji) == self.bot.custom_emoji.get('raid_omw', u'\U0001f3ce\U0000fe0f'):
                await self._rsvp(ctx, "coming", teamcounts)
            elif str(payload.emoji) == self.bot.custom_emoji.get('raid_here', u'\U0001F4CD'):
                await self._rsvp(ctx, "here", teamcounts)
            elif str(payload.emoji) == self.bot.custom_emoji.get('raid_cancel', u'\U0000274C'):
                await self._cancel(ctx)
        elif react_message == "next_trains":
            if str(payload.emoji) == self.bot.custom_emoji.get('train_emoji', u'\U0001F682'):
                next_train = self.bot.guild_dict[guild.id].get(report_dict, {})[channel.id]['next_trains'][message.id]
                if user.id == next_train.get('author'):
                    return
                next_channel = self.bot.get_channel(next_train['channel'])
                teamcounts = ""
                for trainer in self.bot.guild_dict[guild.id].get(report_dict, {})[channel.id]['trainer_dict']:
                    if trainer == user.id:
                        teamcounts = get_teamcounts(channel, trainer, self.bot.guild_dict[guild.id].get(report_dict, {})[channel.id]['trainer_dict'])
                        break
                if not teamcounts:
                    for trainer in self.bot.guild_dict[guild.id].get(report_dict, {})[channel.id].get('lobby', {}).get('starting_dict', {}):
                        if trainer == user.id:
                            teamcounts = get_teamcounts(channel, trainer, self.bot.guild_dict[guild.id].get(report_dict, {})[channel.id].get('lobby', {}).get('starting_dict', {}))
                            break
                if not teamcounts:
                    for lobby in self.bot.guild_dict[guild.id].get(report_dict, {})[channel.id].get('battling', []):
                        for trainer in lobby['starting_dict']:
                            if trainer == user.id:
                                teamcounts = get_teamcounts(channel, trainer, lobby['starting_dict'])
                                break
                if not teamcounts:
                    for lobby in self.bot.guild_dict[guild.id].get(report_dict, {})[channel.id].get('completed', []):
                        for trainer in lobby['starting_dict']:
                            if trainer == user.id:
                                teamcounts = get_teamcounts(channel, trainer, lobby['starting_dict'])
                                break
                if not teamcounts:
                    teamcounts = "1"
                ctx.message.author, ctx.author = user, user
                ctx.message.channel, ctx.channel = next_channel, next_channel
                await self._rsvp(ctx, "coming", teamcounts)
                await asyncio.sleep(1)
                self.bot.guild_dict[guild.id].get(report_dict, {})[next_channel.id]['trainer_dict'][user.id]['train'] = True

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        guild = message.guild
        channel = message.channel
        author = message.author
        if not channel or not author or not guild:
            return
        if guild.id not in list(self.bot.guild_dict.keys()):
            return
        report_dict = await utils.get_report_dict(self.bot, channel)
        if message.author == self.bot.user and report_dict:
            if message.id == self.bot.guild_dict.get(guild.id, {}).get(report_dict, {}).get(message.channel.id, {}).get('raid_message'):
                raid_message = await channel.send(message.content, embed=message.embeds[0] if message.embeds else None)
                for reaction in message.reactions:
                    await utils.add_reaction(raid_message, reaction.emoji)
                self.bot.guild_dict[guild.id][report_dict][message.channel.id]['raid_message'] = raid_message.id
            elif message.id == self.bot.guild_dict.get(guild.id, {}).get(report_dict, {}).get(message.channel.id, {}).get('weather_msg'):
                weather_msg = await channel.send(message.content, embed=message.embeds[0] if message.embeds else None)
                self.bot.guild_dict[guild.id][report_dict][message.channel.id]['weather_msg'] = weather_msg.id
            elif message.id == self.bot.guild_dict.get(guild.id, {}).get(report_dict, {}).get(message.channel.id, {}).get('timerset_msg'):
                timerset_msg = await channel.send(message.content, embed=message.embeds[0] if message.embeds else None)
                self.bot.guild_dict[guild.id][report_dict][message.channel.id]['timerset_msg'] = timerset_msg.id
            elif message.id == self.bot.guild_dict.get(guild.id, {}).get(report_dict, {}).get(message.channel.id, {}).get('ctrsmessage'):
                ctrsmessage = await channel.send(message.content, embed=message.embeds[0] if message.embeds else None)
                for reaction in message.reactions:
                    await utils.add_reaction(ctrsmessage, reaction.emoji)
                self.bot.guild_dict[guild.id][report_dict][message.channel.id]['ctrsmessage'] = ctrsmessage.id
        if channel.id in self.bot.guild_dict.get(guild.id, {}).get(report_dict, {}) and self.bot.guild_dict[guild.id]['configure_dict'].setdefault('archive', {}).setdefault('enabled', False):
            if message.content.strip() == "!archive":
                self.bot.guild_dict[guild.id][report_dict][channel.id]['archive'] = True
            if self.bot.guild_dict[guild.id][report_dict][channel.id].get('archive', False):
                logs = self.bot.guild_dict[guild.id][report_dict][channel.id].get('logs', {})
                logs[message.id] = {'author_id': message.author.id, 'author_str': str(message.author), 'author_avy':str(message.author.avatar_url), 'author_nick':message.author.nick, 'color_int':message.author.color.value, 'content': message.clean_content, 'created_at':message.created_at}
                self.bot.guild_dict[guild.id][report_dict][channel.id]['logs'] = logs

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild and message.guild.id in self.bot.guild_dict.keys():
            for report_dict in self.bot.channel_report_dicts:
                report_dict = self.bot.guild_dict[message.guild.id].setdefault(report_dict, {})
            report_dict = await utils.get_report_dict(self.bot, message.channel)
            channel_status = self.bot.guild_dict[message.guild.id].get(report_dict, {}).get(message.channel.id, None)
            if channel_status:
                if self.bot.guild_dict[message.guild.id]['configure_dict'].get('archive', {}).get('enabled', False) and self.bot.guild_dict[message.guild.id]['configure_dict'].get('archive', {}).get('list', []):
                    for phrase in self.bot.guild_dict[message.guild.id]['configure_dict']['archive']['list']:
                        if phrase in message.content:
                            self.bot.guild_dict[message.guild.id][report_dict][message.channel.id]['archive'] = True
                if self.bot.guild_dict[message.guild.id][report_dict][message.channel.id]['active']:
                    trainer_dict = self.bot.guild_dict[message.guild.id][report_dict][message.channel.id]['trainer_dict']
                    ctx = await self.bot.get_context(message)
                    omw_emoji = utils.parse_emoji(message.guild, self.bot.config.omw_id)
                    here_emoji = utils.parse_emoji(message.guild, self.bot.config.here_id)
                    if message.author.id in trainer_dict:
                        count = trainer_dict[message.author.id].get('count', 1)
                    else:
                        count = 1
                    if message.content.startswith("❓"):
                        emoji_count = message.content.count("❓")
                        return await self._rsvp(ctx, "maybe", str(emoji_count))
                    elif message.content.startswith(omw_emoji):
                        emoji_count = message.content.count(omw_emoji)
                        return await self._rsvp(ctx, "coming", str(emoji_count))
                    elif message.content.startswith(here_emoji) or message.content.startswith("🚁"):
                        emoji_count = message.content.count(here_emoji)
                        if not emoji_count:
                            emoji_count = message.content.count("🚁")
                        return await self._rsvp(ctx, "here", str(emoji_count))
                    elif message.content.startswith("❌"):
                        return await self._cancel(ctx)
                    if "/maps" in message.content and "http" in message.content and 'raidchannel' in report_dict:
                        newcontent = message.content.replace("<", "").replace(">", "")
                        newloc = utils.create_gmaps_query(self.bot, newcontent, message.channel, type=self.bot.guild_dict[message.guild.id][report_dict][message.channel.id]['type'])
                        oldraidmsg = await message.channel.fetch_message(self.bot.guild_dict[message.guild.id][report_dict][message.channel.id]['raid_message'])
                        report_channel = self.bot.get_channel(self.bot.guild_dict[message.guild.id][report_dict][message.channel.id]['report_channel'])
                        oldreportmsg = await report_channel.fetch_message(self.bot.guild_dict[message.guild.id][report_dict][message.channel.id]['raid_report'])
                        oldembed = oldraidmsg.embeds[0]
                        newembed = discord.Embed(title=oldembed.title, description=oldembed.description, url=newloc, colour=message.guild.me.colour)
                        for field in oldembed.fields:
                            newembed.add_field(name=field.name, value=field.value, inline=field.inline)
                        newembed.set_footer(text=oldembed.footer.text, icon_url=oldembed.footer.icon_url)
                        newembed.set_thumbnail(url=oldembed.thumbnail.url)
                        newembed.set_author(name=oldembed.author.name, icon_url=oldembed.author.icon_url)
                        try:
                            await oldraidmsg.edit(new_content=oldraidmsg.content, embed=newembed, content=oldraidmsg.content)
                        except:
                            pass
                        try:
                             await oldreportmsg.edit(new_content=oldreportmsg.content, embed=newembed, content=oldreportmsg.content)
                        except:
                            pass
                        self.bot.guild_dict[message.guild.id][report_dict][message.channel.id]['raid_message'] = oldraidmsg.id
                        self.bot.guild_dict[message.guild.id][report_dict][message.channel.id]['raid_report'] = oldreportmsg.id
                        otw_list = []
                        trainer_dict = copy.deepcopy(self.bot.guild_dict[message.guild.id][report_dict][message.channel.id]['trainer_dict'])
                        for trainer in trainer_dict.keys():
                            if trainer_dict[trainer]['status']['coming']:
                                user = message.guild.get_member(trainer)
                                if not user:
                                    continue
                                otw_list.append(user.mention)
                        await message.channel.send(content=_('Meowth! Someone has suggested a different location for the raid! Trainers {trainer_list}: make sure you are headed to the right place!').format(trainer_list=', '.join(otw_list)), embed=newembed)


    """
    Channel Expiration
    """

    async def expiry_check(self, channel):
        guild = channel.guild
        channel = self.bot.get_channel(channel.id)
        if channel.id not in self.bot.active_channels.keys():
            self.bot.active_channels[channel.id] = {}
            logger.info('Channel Added To Watchlist - ' + channel.name)
            await asyncio.sleep(0.5)
            while True:
                wait_time = 30
                try:
                    report_dict = await utils.get_report_dict(self.bot, channel)
                    delete_raid = self.bot.guild_dict[guild.id][report_dict][channel.id].get('delete', False)
                    if delete_raid:
                        self.bot.loop.create_task(self.expire_channel(channel))
                        break
                    if self.bot.guild_dict[guild.id][report_dict][channel.id].get('meetup', {}):
                        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                        start = self.bot.guild_dict[guild.id][report_dict][channel.id]['meetup'].get('start', False)
                        end = self.bot.guild_dict[guild.id][report_dict][channel.id]['meetup'].get('end', False)
                        if start and self.bot.guild_dict[guild.id][report_dict][channel.id]['type'] == 'egg':
                            if start < now:
                                raid_message = await channel.fetch_message(self.bot.guild_dict[guild.id][report_dict][channel.id]['raid_message'])
                                oldembed = raid_message.embeds[0]
                                self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['type'] = 'exraid'
                                self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['egg_level'] = '0'
                                await channel.send(_("The event has started!"), embed=oldembed)
                                await channel.edit(topic="")
                        if end and end < now:
                            self.bot.loop.create_task(self.expire_channel(channel))
                            try:
                                del self.bot.active_channels[channel.id]
                            except KeyError:
                                logger.info('Channel Removal From Active Raid Failed - Not in List - ' + channel.name)
                            logger.info('Channel Expired And Removed From Watchlist - ' + channel.name)
                            break
                        if end and now and (end-now).total_seconds() > 0 and (end-now).total_seconds() < 20:
                            wait_time = (end-now).total_seconds()
                    else:
                        channel_type = self.bot.guild_dict[guild.id][report_dict][channel.id]['type']
                        channel_pokemon = self.bot.guild_dict[guild.id][report_dict][channel.id].get('pkmn_obj')
                        if channel_pokemon and not self.bot.active_channels[channel.id].get('pokemon'):
                            pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, channel_pokemon)
                            self.bot.active_channels[channel.id]['pokemon'] = pokemon
                        elif not channel_pokemon:
                            self.bot.active_channels[channel.id]['pokemon'] = None
                        if self.bot.guild_dict[guild.id][report_dict][channel.id]['active']:
                            if self.bot.guild_dict[guild.id][report_dict][channel.id]['exp'] <= time.time():
                                if channel_type == 'egg':
                                    egg_level = self.bot.guild_dict[guild.id][report_dict][channel.id]['egg_level']
                                    if not channel_pokemon and len(self.bot.raid_info['raid_eggs'][egg_level]['pokemon']) == 1:
                                        channel_pokemon = self.bot.raid_info['raid_eggs'][egg_level]['pokemon'][0]
                                    elif not channel_pokemon and egg_level == "5" and self.bot.guild_dict[channel.guild.id]['configure_dict'].get('settings', {}).get('regional', None) in self.bot.raid_list:
                                        channel_pokemon = self.bot.guild_dict[channel.guild.id]['configure_dict'].get('settings', {}).get('regional', None)
                                    if channel_pokemon:
                                        logger.info('Egg Auto Hatched - ' + channel.name)
                                        try:
                                            del self.bot.active_channels[channel.id]
                                        except KeyError:
                                            pass
                                        await self._eggtoraid(str(channel_pokemon).lower(), channel, author=None)
                                        break
                                self.bot.loop.create_task(self.expire_channel(channel))
                                try:
                                    del self.bot.active_channels[channel.id]
                                except KeyError:
                                    pass
                                logger.info('Channel Expired And Removed From Watchlist - ' + channel.name)
                                break
                            elif (self.bot.guild_dict[guild.id][report_dict][channel.id]['exp'] - time.time()) > 0 and (self.bot.guild_dict[guild.id][report_dict][channel.id]['exp'] - time.time()) < 20:
                                wait_time = (self.bot.guild_dict[guild.id][report_dict][channel.id]['exp'] - time.time())
                        else:
                            self.bot.loop.create_task(self.expire_channel(channel))
                            try:
                                del self.bot.active_channels[channel.id]
                            except KeyError:
                                pass
                            logger.info('Channel Expired And Removed From Watchlist - ' + channel.name)
                            break
                except KeyError:
                    pass
                except Exception as e:
                    logger.critical('Fatal exception', exc_info=e)
                await asyncio.sleep(wait_time)
                continue

    async def expire_channel(self, channel):
        guild = channel.guild
        alreadyexpired = False
        dupechannel = False
        gymhuntrdupe = False
        report_dict = await utils.get_report_dict(self.bot, channel)
        channel_dict = copy.deepcopy(self.bot.guild_dict[guild.id][report_dict][channel.id])
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        logger.info(channel.name)
        channel_exists = self.bot.get_channel(channel.id)
        channel = channel_exists
        report_author = guild.get_member(channel_dict.get('report_author'))
        try:
            del self.bot.active_channels[channel.id]
        except KeyError:
            pass
        if (not channel_exists) and (not self.bot.is_closed()):
            try:
                self.bot.loop.create_task(utils.expire_dm_reports(self.bot, copy.deepcopy(self.bot.guild_dict[guild.id][report_dict].get(channel.id, {}).get('dm_dict', {}))))
                del self.bot.guild_dict[guild.id][report_dict][channel.id]
            except (KeyError, AttributeError):
                pass
            try:
                del self.bot.guild_dict[guild.id]['list_dict']['raid'][channel.id]
            except (KeyError, AttributeError):
                pass
            if gym_matching_cog:
                gym_matching_cog.do_gym_stats(guild.id, channel_dict)
            raid_bonus = channel_dict.get('completed', []) or channel_dict.get('battling', [])
            if raid_bonus and report_author and not report_author.bot:
                raid_reports = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(report_author.id, {}).setdefault('reports', {}).setdefault('raid', 0) + 1
                self.bot.guild_dict[guild.id]['trainers'][report_author.id]['reports']['raid'] = raid_reports
            return
        elif (channel_exists):
            if self.bot.guild_dict[guild.id][report_dict][channel.id]['active'] == False:
                alreadyexpired = True
            else:
                self.bot.guild_dict[guild.id][report_dict][channel.id]['active'] = False
            logger.info('Channel Expired - ' + channel.name)
            dupecount = self.bot.guild_dict[guild.id][report_dict][channel.id].get('duplicate', 0)
            delete_raid = self.bot.guild_dict[guild.id][report_dict][channel.id].get('delete', False)
            egg_level = self.bot.guild_dict[guild.id][report_dict][channel.id]['egg_level']
            report_channel = self.bot.get_channel(self.bot.guild_dict[guild.id][report_dict][channel.id]['report_channel'])
            try:
                reportmsg = await report_channel.fetch_message(self.bot.guild_dict[guild.id][report_dict][channel.id]['raid_report'])
                ctx = await self.bot.get_context(reportmsg)
            except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, AttributeError):
                reportmsg = None
            if dupecount >= 3:
                if report_author.bot:
                    gymhuntrexp = self.bot.guild_dict[guild.id][report_dict][channel.id]['exp']
                    gymhuntrdupe = True
                dupechannel = True
                self.bot.guild_dict[guild.id][report_dict][channel.id]['duplicate'] = 0
                self.bot.guild_dict[guild.id][report_dict][channel.id]['exp'] = time.time()
                if (not alreadyexpired):
                    expire_embed = discord.Embed(colour=channel.guild.me.colour, description=f"The channel has been deleted in 1 minute. Check the channel list for the other raid channel to coordinate in!\nIf this was an error, reset the raid with **!timerset**.")
                    expire_embed.set_author(name=f"Duplicate Reported!")
                    expire_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/unicode_noentry.png?cache=1")
                    await channel.send(embed=expire_embed, delete_after=310)
                    try:
                        timerset_msg = await channel.fetch_message(self.bot.guild_dict[guild.id][report_dict][channel.id]['timerset_msg'])
                        await timerset_msg.edit(content=None, embed=expire_embed)
                    except:
                        pass
                delete_time = (self.bot.guild_dict[guild.id][report_dict][channel.id]['exp'] + (1 * 60)) - time.time()
            elif self.bot.guild_dict[guild.id][report_dict][channel.id]['type'] == 'egg' and not self.bot.guild_dict[guild.id][report_dict][channel.id].get('meetup', {}) and not delete_raid:
                if (not alreadyexpired):
                    pkmn = self.bot.guild_dict[guild.id][report_dict][channel.id].get('pkmn_obj', None)
                    if pkmn:
                        return await self._eggtoraid(pkmn, channel)
                    maybe_list = []
                    trainer_dict = copy.deepcopy(self.bot.guild_dict[guild.id][report_dict][channel.id]['trainer_dict'])
                    for trainer in trainer_dict.keys():
                        if trainer_dict[trainer]['status']['maybe'] or trainer_dict[trainer]['status']['coming'] or trainer_dict[trainer]['status']['here']:
                            user = guild.get_member(trainer)
                            if not user:
                                continue
                            maybe_list.append(user.mention)
                    channel = self.bot.get_channel(channel.id)
                    if not channel:
                        return
                    new_name = await self.edit_channel_name(channel)
                    await channel.edit(name=new_name)
                    if reportmsg:
                        hatch_embed = discord.Embed(colour=channel.guild.me.colour, description=reportmsg.embeds[0].description, title=reportmsg.embeds[0].title, url=reportmsg.embeds[0].url)
                        for field in reportmsg.embeds[0].fields:
                            if _('possible') in field.name.lower() or _('interest') in field.name.lower():
                                hatch_embed.add_field(name=field.name, value=field.value, inline=field.inline)
                    else:
                        hatch_embed = None
                    expire_embed = discord.Embed(colour=channel.guild.me.colour, description=f"Update the raid to the pokemon that hatched using **!raid <pokemon>** or reset the hatch timer with **!timerset**.")
                    expire_embed.set_author(name=f"This egg has hatched!")
                    expire_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/unicode_warning.png?cache=1")
                    try:
                        timerset_msg = await channel.fetch_message(self.bot.guild_dict[guild.id][report_dict][channel.id]['timerset_msg'])
                        await timerset_msg.edit(content=None, embed=expire_embed)
                    except:
                        pass
                    hatch_message = await channel.send(f"**This egg has hatched!** {'Trainers ' if maybe_list else ''}{(', ').join(maybe_list)+': ' if maybe_list else ''}Update the raid to the pokemon that hatched using **!raid <pokemon>** or reset the hatch timer with **!timerset**.", embed=hatch_embed)
                    self.bot.guild_dict[guild.id][report_dict][channel.id]['hatch_message'] = hatch_message.id
                raid_time = int(self.bot.raid_info['raid_eggs'][str(egg_level)]['raidtime'])
                delete_time = (self.bot.guild_dict[guild.id][report_dict][channel.id]['exp'] + (raid_time * 60)) - time.time()
            else:
                if (not alreadyexpired):
                    channel = self.bot.get_channel(channel.id)
                    if not channel:
                        return
                    new_name = await self.edit_channel_name(channel)
                    await channel.edit(name=new_name)
                    expire_embed = discord.Embed(colour=channel.guild.me.colour, description=f"The channel has been deactivated and will be deleted in 5 minutes.\nTo reactivate the channel, use **!timerset** to set the timer again.")
                    expire_embed.set_author(name=f"This channel timer has expired!")
                    expire_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/unicode_noentry.png?cache=1")
                    await channel.send(embed=expire_embed, delete_after=310)
                    try:
                        timerset_msg = await channel.fetch_message(self.bot.guild_dict[guild.id][report_dict][channel.id]['timerset_msg'])
                        await timerset_msg.edit(content=None, embed=expire_embed)
                    except:
                        pass
                delete_time = (self.bot.guild_dict[guild.id][report_dict][channel.id]['exp'] + (5 * 60)) - time.time()
            raidtype = _("event") if self.bot.guild_dict[guild.id][report_dict][channel.id].get('meetup', False) else _(" raid")
            if delete_raid:
                delete_time = 300
            await asyncio.sleep(delete_time)
            # If the channel has already been deleted from the dict, someone
            # else got to it before us, so don't do anything.
            # Also, if the channel got reactivated, don't do anything either.
            try:
                last_report = True if len (self.bot.guild_dict[guild.id][report_dict].keys()) == 1 else False
                channel_type = report_dict.replace('channel_dict', '').replace('_dict', '')
                if self.bot.guild_dict[guild.id][report_dict].get(channel.id, {}).get('active', False):
                    return
                elif (self.bot.guild_dict[guild.id][report_dict][channel.id]['active'] == False) and (not self.bot.is_closed()):
                    if report_channel:
                        # Check message again in case it was edited or hatched
                        try:
                            if reportmsg and "level" in reportmsg.embeds[0].author.name.lower():
                                reportmsg = await report_channel.fetch_message(self.bot.guild_dict[guild.id][report_dict][channel.id]['raid_report'])
                        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, AttributeError):
                            reportmsg = None
                        if self.bot.guild_dict[guild.id][report_dict][channel.id]['type'] == "egg" and not self.bot.guild_dict[guild.id][report_dict][channel.id].get('meetup', {}):
                            expiremsg = _('**This level {level} raid egg has expired!**').format(level=egg_level)
                        else:
                            expiremsg = _('**This {pokemon}{raidtype} has expired!**').format(pokemon=self.bot.guild_dict[guild.id][report_dict][channel.id].get('pkmn_obj', ""), raidtype=raidtype)
                        if dupechannel:
                            await utils.safe_delete(reportmsg)
                        elif reportmsg:
                            cleanup_setting = self.bot.guild_dict[guild.id].get('configure_dict').get(channel_type, {}).setdefault('cleanup_setting', "edit")
                            if cleanup_setting == "edit":
                                try:
                                    await reportmsg.edit(content=reportmsg.content.splitlines()[0], embed=discord.Embed(description=expiremsg, colour=guild.me.colour))
                                    await reportmsg.clear_reactions()
                                except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                                    pass
                            else:
                                try:
                                    await reportmsg.delete()
                                except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                                    pass
                        try:
                            user_message = await report_channel.fetch_message(self.bot.guild_dict[guild.id][report_dict][channel.id]['report_message'])
                            await utils.safe_delete(user_message)
                        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                            pass
                        # channel doesn't exist anymore in serverdict
                    archive = self.bot.guild_dict[guild.id][report_dict][channel.id].get('archive', False)
                    logs = self.bot.guild_dict[guild.id][report_dict][channel.id].get('logs', {})
                    self.bot.loop.create_task(utils.expire_dm_reports(self.bot, self.bot.guild_dict[guild.id][report_dict][channel.id].get('dm_dict', {})))
                    raid_bonus = channel_dict.get('completed', []) or channel_dict.get('battling', [])
                    if raid_bonus and report_author and not report_author.bot:
                        raid_reports = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(report_author.id, {}).setdefault('reports', {}).setdefault('raid', 0) + 1
                        self.bot.guild_dict[guild.id]['trainers'][report_author.id]['reports']['raid'] = raid_reports
                    if gym_matching_cog:
                        gym_matching_cog.do_gym_stats(guild.id, channel_dict)
                    channel_exists = self.bot.get_channel(channel.id)
                    if channel_exists == None:
                        return
                    elif not gymhuntrdupe and not archive and not logs:
                        try:
                            del self.bot.guild_dict[guild.id][report_dict][channel.id]
                        except KeyError:
                            pass
                        try:
                            del self.bot.guild_dict[guild.id]['list_dict']['raid'][channel.id]
                        except KeyError:
                            pass
                        try:
                            await channel_exists.delete()
                        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                            pass
                        logger.info('Channel Deleted - ' + channel.name)
                    elif gymhuntrdupe and not archive:
                        for overwrite in channel.overwrites:
                            try:
                                await channel.set_permissions(guild.default_role, overwrite=discord.PermissionOverwrite(read_messages=False))
                            except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.InvalidArgument):
                                pass
                            if (overwrite.name not in guild.me.top_role.name) and (overwrite.name not in guild.me.name):
                                try:
                                    await channel.set_permissions(overwrite, read_messages=False)
                                except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.InvalidArgument):
                                    pass
                        await channel.send(_('-----------------------------------------------\n**The channel has been removed from view for everybody but Meowth and server owner to protect from future bot reported duplicates. It will be removed on its own, please do not remove it. Just ignore what happens in this channel.**\n-----------------------------------------------'))
                        deltime = ((gymhuntrexp - time.time()) / 60) + 10
                        await self._timerset(channel, deltime)
                    elif archive or logs:
                        try:
                            for overwrite in channel.overwrites:
                                ow = channel.overwrites_for(overwrite)
                                if (overwrite.name not in guild.me.top_role.name) and (overwrite.name not in guild.me.name):
                                    ow.read_messages = False
                                if channel.overwrites_for(overwrite).manage_guild or channel.overwrites_for(overwrite).manage_channels:
                                    ow.read_messages = True
                                await channel.set_permissions(overwrite, overwrite = ow)
                            for role in guild.roles:
                                ow = channel.overwrites_for(role)
                                if role.permissions.manage_guild or role.permissions.manage_channels:
                                    ow.read_messages = True
                                    await channel.set_permissions(role, overwrite = ow)
                            await channel.set_permissions(guild.default_role, read_messages=False)
                        except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.InvalidArgument):
                            pass
                        archive_emoji = self.bot.custom_emoji.get('archive_emoji', u'\U0001f4e5')
                        channel = self.bot.get_channel(channel.id)
                        if not channel:
                            return
                        if archive_emoji not in channel.name:
                            new_name = f"{archive_emoji}-{channel.name}"
                            category = self.bot.guild_dict[guild.id]['configure_dict'].get('archive', {}).get('category', 'same')
                            if category == 'same':
                                newcat = channel.category
                            else:
                                newcat = guild.get_channel(category)
                            try:
                                await channel.edit(name=new_name, category=newcat)
                            except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                                pass
                            await channel.send(_('-----------------------------------------------\n**The channel has been archived and removed from view for everybody but Meowth and those with Manage Channel permissions. Any messages that were deleted after the channel was marked for archival will be posted below. You will need to delete this channel manually or use !recover**\n-----------------------------------------------'))
                            while logs:
                                earliest = min(logs)
                                embed = discord.Embed(colour=logs[earliest]['color_int'], description=logs[earliest]['content'], timestamp=logs[earliest]['created_at'])
                                if logs[earliest]['author_nick']:
                                    embed.set_author(name="{name} [{nick}]".format(name=logs[earliest]['author_str'], nick=logs[earliest]['author_nick']), icon_url = logs[earliest]['author_avy'])
                                else:
                                    embed.set_author(name=logs[earliest]['author_str'], icon_url = logs[earliest]['author_avy'])
                                await channel.send(embed=embed)
                                del logs[earliest]
                                await asyncio.sleep(.25)
                            try:
                                del self.bot.guild_dict[guild.id][report_dict][channel.id]
                            except KeyError:
                                pass
                            try:
                                del self.bot.guild_dict[guild.id]['list_dict']['raid'][channel.id]
                            except KeyError:
                                pass
                try:
                    if last_report and reportmsg and len(self.bot.guild_dict[guild.id][report_dict].keys()) == 0:
                        return await ctx.invoke(self.bot.get_command('list'))
                except:
                    pass
                try:
                    if channel.category and channel.category.id in self.bot.guild_dict[guild.id]['configure_dict'][channel_type].get('overflow_list', []):
                        if len(channel.category.channels) == 0:
                            await channel.category.delete()
                            self.bot.guild_dict[guild.id]['configure_dict'][channel_type]['overflow_list'] = [x for x in self.bot.guild_dict[guild.id]['configure_dict'][channel_type]['overflow_list'] if guild.get_channel(x)]
                except Exception as e:
                    pass
            except KeyError:
                pass

    @tasks.loop(seconds=600)
    async def channel_cleanup(self, loop=True):
        logger.info('------ BEGIN ------')
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        # clean up active_channels
        for channel_id in self.bot.active_channels.keys():
            channel = self.bot.get_channel(channel_id)
            if not channel:
                try:
                    del self.bot.active_channels[channel_id]
                except KeyError:
                    pass
        # for every server in save data
        for guild in list(self.bot.guilds):
            if guild.id not in list(self.bot.guild_dict.keys()):
                continue
            try:
                logger.info(f"Server: ({guild.name}) - BEGIN CHECKING SERVER")
                # clear channel lists
                dict_channel_delete = []
                # check every raid channel data for each server
                report_channel_dict = {}
                for report_dict in self.bot.channel_report_dicts:
                    report_channel_dict = {**report_channel_dict, **self.bot.guild_dict[guild.id].setdefault(report_dict, {})}
                for channelid in report_channel_dict:
                    channel = self.bot.get_channel(channelid)
                    report_dict = await utils.get_report_dict(self.bot, channel)
                    logger.info(f"Server: {guild.name} : Channel: {channelid} - CHECKING")
                    channel_dict = self.bot.guild_dict[guild.id].get(report_dict, {}).get(channelid, {})
                    report_author = guild.get_member(channel_dict.get('report_author'))
                    if channel == None:
                        for report_dict in self.bot.channel_report_dicts:
                            channel_dict = self.bot.guild_dict[guild.id].get(report_dict, {}).get(channelid, {})
                            if channel_dict:
                                break
                        # list channel for deletion from save data
                        dict_channel_delete.append(channelid)
                        report_author = guild.get_member(channel_dict.get('report_author'))
                        if channel_dict and 'raidchannel' in report_dict:
                            if gym_matching_cog:
                                gym_matching_cog.do_gym_stats(guild.id, channel_dict)
                            self.bot.loop.create_task(utils.expire_dm_reports(self.bot, self.bot.guild_dict[guild.id][report_dict].get(channelid, {}).get('dm_dict', {})))
                            raid_bonus = channel_dict.get('completed', []) or channel_dict.get('battling', [])
                            if raid_bonus and report_author and not report_author.bot:
                                raid_reports = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(report_author.id, {}).setdefault('reports', {}).setdefault('raid', 0) + 1
                                self.bot.guild_dict[guild.id]['trainers'][report_author.id]['reports']['raid'] = raid_reports
                        try:
                            report_channel = self.bot.get_channel(channel_dict['report_channel'])
                            report_message = await report_channel.fetch_message(channel_dict.get('raid_report'))
                            raid_type = "event" if channel_dict.get('meetup', False) else " raid"
                            if raid_type != "event" and channel_dict['type'] == "egg":
                                expiremsg = f"**This level {channel_dict['egg_level']} raid egg has expired!**"
                            else:
                                expiremsg = f"**This {channel_dict.get('pkmn_obj', '')}{raid_type} has expired!**"
                            channel_type = report_dict.replace('channel_dict', '').replace('_dict', '')
                            cleanup_setting = self.bot.guild_dict[guild.id].get('configure_dict').get(channel_type, {}).setdefault('cleanup_setting', "edit")
                            if cleanup_setting == "edit":
                                try:
                                    await report_message.edit(content=report_message.content.splitlines()[0], embed=discord.Embed(description=expiremsg, colour=guild.me.colour))
                                    await report_message.clear_reactions()
                                except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                                    pass
                            else:
                                try:
                                    await report_message.delete()
                                except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                                    pass
                            user_message = await report_channel.fetch_message(channel_dict['report_message'])
                            await utils.safe_delete(user_message)
                        except:
                            pass
                        logger.info(f"Server: {guild.name} : Channel: {channelid} - DOESN'T EXIST IN DISCORD -> DELETING")
                    # otherwise, if meowth can still see the channel in discord
                    else:
                        logger.info(f"Server: {guild.name} : Channel: {channelid} ({channel.name}) - EXISTS IN DISCORD")
                        # if the channel save data shows it's not an active raid
                        if channel_dict['active'] == False:
                            if channel_dict['type'] == 'egg':
                                # and if it has been expired for longer than 45 minutes already
                                if channel_dict['exp'] < (time.time() - (45 * 60)):
                                    logger.info(f"Server: {guild.name} : Channel: {channelid} ({channel.name}) - 45+ MIN EXPIRY NONACTIVE EGG -> Expire_Channel")
                                # and if it has been expired for longer than 5 minutes already
                            elif channel_dict['exp'] < (time.time() - (5 * 60)):
                                    #list the channel to be deleted
                                logger.info(f"Server: {guild.name} : Channel: {channelid} ({channel.name}) - 5+ MIN EXPIRY NONACTIVE RAID -> Expire_Channel")
                            logger.info(f"Server: {guild.name} : Channel: {channelid} ({channel.name}) - RECENTLY EXPIRED NONACTIVE RAID -> Expire_Channel")
                        # if the channel save data shows it as an active raid still
                        elif channel_dict['active'] == True:
                            # if channel is still active, make sure it's expiry is being monitored
                            if channel.id not in self.bot.active_channels.keys():
                                logger.info(f"Server: {guild.name} : Channel: {channelid} ({channel.name}) - MISSING FROM EXPIRY CHECK -> Expiry_Check")
                        self.bot.loop.create_task(self.expiry_check(channel))
                # for every channel listed to have save data deleted
                for c in dict_channel_delete:
                    for report_dict in self.bot.channel_report_dicts:
                        try:
                            del self.bot.guild_dict[guild.id][report_dict][c]
                            logger.info(f"{guild.id} - RaidChannel ({c}) Savedata Cleared")
                        except KeyError:
                            pass
                    try:
                        del self.bot.guild_dict[guild.id]['list_dict']['raid'][c]
                    except KeyError:
                        pass
            except Exception as e:
                print(traceback.format_exc())
        # save server_dict changes after cleanup
        logger.info('SAVING CHANGES')
        try:
            await self.bot.save
        except Exception as err:
            logger.info('SAVING FAILED' + err)
        logger.info('------ END ------')
        if not loop:
            return

    @channel_cleanup.before_loop
    async def before_channel_cleanup(self):
        await self.bot.wait_until_ready()

    """
    Helpers
    """

    async def send_dm_messages(self, ctx, pokemon_or_level, raid_details, content, embed, dm_dict):
        if embed:
            if isinstance(embed.description, discord.embeds._EmptyEmbed):
                embed.description = ""
            if "Jump to Message" not in embed.description:
                embed.description = embed.description + f"\n**Report:** [Jump to Message]({ctx.raidreport.jump_url})"
        content = content.splitlines()[0]
        egg_level = None
        index = 0
        for field in embed.fields:
            if "list" in field.name.lower():
                embed.remove_field(index)
            else:
                index += 1
        if pokemon_or_level.isdigit() or pokemon_or_level.upper() == "EX":
            egg_level = pokemon_or_level.upper()
        if self.bot.active_channels.get(ctx.raidreport.channel.id, {}).get('pokemon', None):
            pokemon = self.bot.active_channels[ctx.raid_report.channel.id]['pokemon']
        else:
            pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, pokemon_or_level)
        raid_types = ['None']
        if pokemon:
            raid_types = pokemon.types.copy()
        raid_types.append('None')
        for trainer in self.bot.guild_dict[ctx.guild.id].get('trainers', {}):
            user_link = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(trainer, {}).setdefault('alerts', {}).setdefault('settings', {}).setdefault('link', True)
            if user_link:
                user_wants = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(trainer, {}).setdefault('alerts', {}).setdefault('wants', [])
                user_forms = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(trainer, {}).setdefault('alerts', {}).setdefault('forms', [])
            else:
                user_wants = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(trainer, {}).setdefault('alerts', {}).setdefault('bosses', [])
                user_forms = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(trainer, {}).setdefault('alerts', {}).setdefault('boss_forms', [])
            pokemon_setting = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].get('alerts', {}).get('settings', {}).get('categories', {}).get('pokemon', {}).get('raid', True)
            user_types = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('types', [])
            type_setting = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].get('alerts', {}).get('settings', {}).get('categories', {}).get('type', {}).get('raid', True)
            user_gyms = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('gyms', [])
            user_eggs = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('raid_eggs', [])
            user_custom = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('custom', {})
            if not any([user_wants, user_forms, pokemon_setting, user_types, type_setting, user_gyms, user_custom]):
                continue
            if not checks.dm_check(ctx, trainer, "raid") or trainer in dm_dict:
                continue
            send_raid = []
            if pokemon_setting and pokemon and pokemon.id in user_wants:
                send_raid.append(f"{'Pokemon' if user_link else 'Boss'}: {pokemon.name.title()}")
            if pokemon_setting and pokemon and str(pokemon) in user_forms:
                send_raid.append(f"{'Pokemon' if user_link else 'Boss'} Form: {str(pokemon)}")
            if user_custom:
                for custom in user_custom:
                    if "Custom" in send_raid:
                        break
                    name_check = str(pokemon).replace("Male", "").replace("Female", "").replace("XS", "").replace("XL", "")
                    if name_check != user_custom[custom].get('pokemon', ''):
                        continue
                    if "raid" not in user_custom[custom].get('report_types'):
                        continue
                    send_raid.append("Custom")
            if type_setting and raid_types[0].lower() in user_types:
                type_emoji = utils.parse_emoji(ctx.guild, self.bot.config.type_id_dict[raid_types[0].lower()])
                send_raid.append(f"Type: {type_emoji}")
            if type_setting and raid_types[1].lower() in user_types:
                type_emoji = utils.parse_emoji(ctx.guild, self.bot.config.type_id_dict[raid_types[1].lower()])
                send_raid.append(f"Type: {type_emoji}")
            if egg_level and egg_level in user_eggs:
                send_raid.append(f"Raid Egg: {egg_level}")
            if raid_details.lower() in user_gyms:
                send_raid.append(f"Gym: {raid_details.title()}")
            if send_raid:
                embed.description = embed.description + f"\n**Subscription:** {(', ').join(send_raid)}"
                try:
                    user = ctx.guild.get_member(trainer)
                    raiddmmsg = await user.send(content=content, embed=embed)
                    dm_dict[user.id] = raiddmmsg.id
                except discord.errors.Forbidden:
                    pass
                embed.description = embed.description.replace(f"\n**Subscription:** {(', ').join(send_raid)}", "")
        return dm_dict

    async def edit_dm_messages(self, ctx, content, embed, dm_dict):
        report_dict = await utils.get_report_dict(self.bot, ctx.raid_channel)
        dm_dict = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.raid_channel.id].get('dm_dict', {})
        if isinstance(embed.description, discord.embeds._EmptyEmbed):
            embed.description = ""
        if "Jump to Message" not in embed.description:
            embed.description = embed.description + f"\n**Report:** [Jump to Message]({ctx.raidreport.jump_url})"
        new_description = str(embed.description)
        for dm_user, dm_message in dm_dict.items():
            try:
                dm_user = self.bot.get_user(dm_user)
                dm_channel = dm_user.dm_channel
                if not dm_channel:
                    dm_channel = await dm_user.create_dm()
                if not dm_user or not dm_channel:
                    continue
                dm_message = await dm_channel.fetch_message(dm_message)
                embed.description = dm_message.embeds[0].description
                await dm_message.edit(content=content.splitlines()[0], embed=embed)
            except:
                pass
        embed.description = new_description
        pokemon_or_level = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.raid_channel.id].get('pkmn_obj')
        if not pokemon_or_level:
            pokemon_or_level = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.raid_channel.id].get('egg_level')
        raid_details = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.raid_channel.id].get('address')
        dm_dict = await self.send_dm_messages(ctx, str(pokemon_or_level), raid_details, ctx.raidreport.content.splitlines()[0].replace(ctx.author.mention, f"{ctx.author.display_name} in {ctx.channel.mention}"), copy.deepcopy(embed), dm_dict)
        self.bot.guild_dict[ctx.guild.id][report_dict][ctx.raid_channel.id]['dm_dict'] = dm_dict

    async def edit_channel_name(self, channel):
        type = None
        channel_emoji = ""
        channel_name = ""
        rsvp_emoji = self.bot.custom_emoji.get('rsvp_emoji', u"\U0001f4ac")
        hatch_emoji = self.bot.custom_emoji.get('hatch_emoji', u"\U000026a0\U0000fe0f")
        expire_emoji  = self.bot.custom_emoji.get('expire_emoji', u"\U000026d4")
        starting_emoji = self.bot.custom_emoji.get('starting_emoji', u"\U000025b6\U0000fe0f")
        battling_emoji = self.bot.custom_emoji.get('battling_emoji', u"\U0001f4a5")
        completed_emoji = self.bot.custom_emoji.get('completed_emoji', u"\U00002705")
        for report_dict in self.bot.channel_report_dicts:
            if channel.id in list(self.bot.guild_dict[channel.guild.id][report_dict].keys()):
                type = report_dict.replace('raidchannel_dict', 'raid').replace('exraidchannel_dict', 'exraid').replace('meetup_dict', 'meetup').replace('raidtrain_dict', 'train')
                break
        channel_dict = self.bot.guild_dict[channel.guild.id].get(report_dict, {}).get(channel.id, {})
        if not channel_dict:
            return channel.name
        if "raid" in type and channel_dict['type'] == "egg":
            type = "egg"
        channel_address = channel_dict['address']
        channel_address = re.sub('[^a-zA-Z0-9 \-]', '', channel_address)
        channel_address = channel_address.replace(' ', '-')
        channel_expire = channel_dict['exp']
        channel_party, __= await self._get_party(channel)
        channel_lobby = channel_dict.get('lobby', None)
        channel_battle = channel_dict.get('battling', None)
        channel_complete = channel_dict.get('completed', None)
        channel_delete = channel_dict.get('delete', False)
        if self.bot.active_channels.get(channel.id, {}).get('pokemon', None):
            channel_boss = self.bot.active_channels[channel.id]['pokemon']
        else:
            channel_boss = await pkmn_class.Pokemon.async_get_pokemon(self.bot, channel_dict.get('pkmn_obj', None))
        channel_level = channel_dict['egg_level']
        if type != 'egg' and time.time() > channel_expire:
            channel_emoji += f"{expire_emoji}-"
        elif channel_party['maybe'] + channel_party['coming'] + channel_party['here'] > 0:
            channel_emoji += f"{rsvp_emoji}-"
        if type == "egg" and time.time() > channel_expire:
            channel_emoji += f"{hatch_emoji}-"
        if channel_lobby:
            channel_emoji += f"{starting_emoji}-"
        elif channel_battle:
            channel_emoji += f"{battling_emoji}-"
        elif channel_complete:
            channel_emoji += f"{completed_emoji}-"
        if channel_delete:
            channel_emoji = f"{expire_emoji}-"
        if type == "train" or type == "meetup":
            channel_title = channel_dict.get('meetup', {}).get('channel_name', channel.name.split(f"{type}-")[1])
            channel_name = f"{channel_emoji}{type}-{channel_title}"
        elif type == "egg":
            if channel_level == "EX":
                channel_name = f"{channel_emoji}ex-egg-{channel_address.lower()}"
            else:
                channel_name = f"{channel_emoji}{channel_level}-egg-{channel_address.lower()}"
        elif type == "raid" or type == "exraid":
            channel_name = f"{channel_emoji}{channel_boss.name.lower()}-{channel_boss.region.lower()+'-' if channel_boss and channel_boss.region else ''}-{channel_boss.form.lower()+'-' if channel_boss and channel_boss.form else ''}-{channel_address.lower()}"
        else:
            channel_name = f"{channel_emoji}{type}-{channel_address.lower()}"
        return channel_name

    async def create_raid_channel(self, ctx, entered_raid, raid_details, type):
        message = ctx.message
        channel = ctx.channel
        raid_channel_overwrites = ctx.channel.overwrites
        raid_channel_overwrites[self.bot.user] = discord.PermissionOverwrite(send_messages=True, read_messages=True, manage_roles=True)
        category_choices = []
        if type == "raid":
            raid_channel_name = (entered_raid + '-')
            raid_channel_category = utils.get_category(self.bot, ctx.channel, utils.get_level(self.bot, entered_raid), category_type="raid")
            overflow_list = self.bot.guild_dict[ctx.guild.id]['configure_dict'].setdefault('raid', {}).setdefault('overflow_list', [])
        elif type == "egg":
            raid_channel_name = _('{egg_level}-egg-').format(egg_level=entered_raid)
            raid_channel_category = utils.get_category(self.bot, ctx.channel, entered_raid, category_type="raid")
            overflow_list = self.bot.guild_dict[ctx.guild.id]['configure_dict'].setdefault('raid', {}).setdefault('overflow_list', [])
        elif type == "exraid":
            raid_channel_name = _('ex-egg-')
            raid_channel_category = utils.get_category(self.bot, ctx.channel, "EX", category_type="exraid")
            overflow_list = self.bot.guild_dict[ctx.guild.id]['configure_dict'].setdefault('exraid', {}).setdefault('overflow_list', [])
            if self.bot.guild_dict[ctx.guild.id]['configure_dict'].setdefault('exraid', {}).setdefault('permissions', 'everyone') == "everyone":
                raid_channel_overwrites[ctx.guild.default_role] = discord.PermissionOverwrite(read_messages=True)
        elif type == "meetup":
            raid_channel_name = _('meetup-')
            raid_channel_category = utils.get_category(self.bot, ctx.channel, None, category_type="meetup")
            overflow_list = self.bot.guild_dict[ctx.guild.id]['configure_dict'].setdefault('meetup', {}).setdefault('overflow_list', [])
        elif type == "train":
            raid_channel_name = _('train-')
            raid_channel_category = utils.get_category(self.bot, ctx.channel, None, category_type="train")
            overflow_list = self.bot.guild_dict[ctx.guild.id]['configure_dict'].setdefault('train', {}).setdefault('overflow_list', [])
        raid_channel_name += utils.sanitize_channel_name(raid_details)
        if raid_channel_category:
            if overflow_list:
                for cat in overflow_list:
                    cat = discord.utils.get(ctx.guild.categories, id=cat)
                    category_choices.insert(0, cat)
            category_choices.insert(0, raid_channel_category)
        else:
            category_choices = [None]
        if type != "exraid":
            ow = ctx.channel.overwrites_for(ctx.guild.default_role)
            ow.send_messages = True
            raid_channel_overwrites[ctx.guild.default_role] = ow
        for role in ctx.guild.roles:
            if role.permissions.manage_guild or role.permissions.manage_channels or role.permissions.manage_messages:
                ow = ctx.channel.overwrites_for(role)
                ow.manage_channels = True
                ow.manage_messages = True
                ow.manage_roles = True
                ow.send_messages = True
                raid_channel_overwrites[role] = ow
        for category in category_choices:
            if not category:
                continue
            try:
                raid_channel = await ctx.guild.create_text_channel(raid_channel_name, overwrites=raid_channel_overwrites, category=category)
                break
            except:
                raid_channel = None
        if not raid_channel and raid_channel_category:
            overflow_category = await ctx.guild.create_category(raid_channel_category.name, overwrites=raid_channel_overwrites)
            try:
                await overflow_category.edit(position=raid_channel_category.position)
            except:
                pass
            overflow_list.append(overflow_category.id)
            raid_channel = await ctx.guild.create_text_channel(raid_channel_name, overwrites=raid_channel_overwrites, category=overflow_category)
        if not raid_channel:
            category_choices = [ctx.channel.category, None]
            for category in category_choices:
                try:
                    raid_channel = await ctx.guild.create_text_channel(raid_channel_name, overwrites=raid_channel_overwrites, category=category)
                    break
                except:
                    raid_channel = None
        if not raid_channel:
            return None
        return raid_channel

    async def make_raid_embed(self, ctx, report_details, raidexp=None):
        message = ctx.message
        if not ctx.prefix:
            prefix = self.bot._get_prefix(self.bot, ctx.message)
            ctx.prefix = prefix[-1]
        timestamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))).strftime(_('%I:%M %p (%H:%M)'))
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
        raid_coordinates = report_details.get('coordinates', None)
        raid_location = report_details.get('address', None)
        pokemon = report_details.get('pkmn_obj', None)
        if pokemon:
            pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, pokemon)
        weather = report_details.get('weather', None)
        egg_level = report_details.get('egg_level', "0")
        moveset = report_details.get('moves', None)
        embed_type = "raid" if pokemon else "egg"
        if raid_coordinates:
            raid_gmaps_link = f"https://www.google.com/maps/search/?api=1&query={raid_coordinates}"
        else:
            raid_gmaps_link = utils.create_gmaps_query(self.bot, raid_location or raid_coordinates, ctx.channel, type="raid")
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        gym_info = ""
        if gym_matching_cog and not raid_coordinates:
            gym_info, raid_location, gym_url = await gym_matching_cog.get_poi_info(ctx, raid_location, "raid", dupe_check=False, autocorrect=False)
            if gym_url:
                raid_gmaps_link = gym_url
        if not raid_location and not raid_coordinates:
            return None
        egg_level = str(egg_level)
        egg_info = ctx.bot.raid_info['raid_eggs'].get(egg_level, {"pokemon":[pokemon]})
        boss_list = []
        for boss in self.bot.raid_dict.get(str(egg_level), []):
            if isinstance(boss, pkmn_class.Pokemon):
                shiny_str = ""
                if "raid" in boss.shiny_available:
                    shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
                boss_list.append(f"{shiny_str}{str(boss)} {boss.emoji}")
        if pokemon and weather:
            if "rain" in weather:
                pokemon.weather = "rainy"
            elif "partly" in weather:
                pokemon.weather = "partlycloudy"
            elif "clear" in weather:
                pokemon.weather = "clear"
            elif "cloudy" in weather:
                pokemon.weather = "cloudy"
            elif "windy" in weather:
                pokemon.weather = "windy"
            elif "snow" in weather:
                pokemon.weather = "snowy"
            elif "fog" in weather:
                pokemon.weather = "foggy"
        raid_img_url = f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/eggs/{egg_level}.png?cache=1" if embed_type == "egg" else pokemon.img_url
        raid_img_url = f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/tx_raid_coin_exclusive.png?cache=1" if egg_level == "EX" else raid_img_url
        report_dict = await utils.get_report_dict(ctx.bot, ctx.channel)
        if report_dict:
            report_message = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['report_message']
            raid_report = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['raid_report']
            raid_img_url = f"{raid_img_url}&report_message={report_message}&raid_report={raid_report}"
        if embed_type == "egg":
            raid_embed = discord.Embed(title=f"Meowth! Click here for directions to the coming level {egg_level} raid!", description=gym_info, url=raid_gmaps_link, colour=ctx.guild.me.colour)
            if len(egg_info['pokemon']) > 1:
                raid_embed.add_field(name=_('**Possible Bosses:**'), value=_('{bosslist1}').format(bosslist1='\n'.join(boss_list[::2])), inline=True)
                raid_embed.add_field(name=_('**Possible Bosses:**'), value=_('{bosslist2}').format(bosslist2='\n'.join(boss_list[1::2])), inline=True)
            else:
                pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, egg_info['pokemon'][0])
                raid_embed.add_field(name=_('**Possible Bosses:**'), value=_('{bosslist}').format(bosslist=''.join(boss_list)), inline=True)
                raid_embed.add_field(name=_('**Weaknesses:**'), value=f"{pokemon.weakness_emoji}\u200b", inline=True)
            raid_embed.set_author(name=f"Level {egg_level} Raid Report", icon_url=raid_img_url)
        elif embed_type == "raid":
            egg_level = utils.get_level(ctx.bot, str(pokemon))
            shiny_str = ""
            if "raid" in pokemon.shiny_available:
                shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
            raid_embed = discord.Embed(title=f"Meowth! Click here for directions to the level {egg_level} raid!", description=gym_info, url=raid_gmaps_link, colour=ctx.guild.me.colour)
            raid_embed.add_field(name=_('**Details:**'), value=f"{shiny_str}{str(pokemon)} {pokemon.emoji}\n{pokemon.is_boosted if pokemon.is_boosted else ''}", inline=True)
            raid_embed.add_field(name=_('**Weaknesses:**'), value=_('{weakness_list}\u200b').format(weakness_list=pokemon.weakness_emoji), inline=True)
            raid_embed.set_author(name=f"{pokemon.name.title()} Raid Report", icon_url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/tx_raid_coin.png?cache=1")
        raid_embed.add_field(name=_('**Next Group:**'), value=f"Set with **{ctx.prefix}starttime**", inline=True)
        if raidexp or raidexp is 0:
            raid_expire = now + datetime.timedelta(minutes=float(raidexp))
            raid_embed.add_field(name=f"{'**Hatches:**' if embed_type == 'egg' else '**Expires:**'}", value=raid_expire.strftime(_('%B %d at %I:%M %p (%H:%M)')), inline=True)
        else:
            raid_embed.add_field(name=f"{'**Hatches:**' if embed_type == 'egg' else '**Expires:**'}", value=f"Set with **{ctx.prefix}timerset**", inline=True)
        if moveset and embed_type == "raid":
            moveset = moveset.split(' / ')
            for index, m in enumerate(moveset):
                if m.lower() in self.bot.move_info.keys():
                    moveset[index] = f"{m} {utils.type_to_emoji(self.bot, self.bot.move_info[m.lower()]['type'])}"
            raid_embed.add_field(name=_("**Moveset:**"), value=(' / ').join([x.title() for x in moveset]))
        raid_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=ctx.author.display_name, timestamp=timestamp), icon_url=ctx.author.avatar_url_as(format=None, static_format='jpg', size=32))
        raid_embed.set_thumbnail(url=raid_img_url)
        return raid_embed

    async def auto_weather(self, ctx, coord):
        wild_dict = self.bot.guild_dict[ctx.guild.id].setdefault('wildreport_dict', {})
        wild_weather_dict = {}
        for wild_report in list(wild_dict.keys()):
            report_time = datetime.datetime.utcfromtimestamp(wild_dict.get(wild_report, {}).get('report_time', time.time()))
            coordinates = wild_dict.get(wild_report, {}).get('coordinates', None)
            weather = wild_dict.get(wild_report, {}).get('weather', None)
            if weather and coordinates and ctx.message.created_at.hour == report_time.hour:
                wild_weather_dict[coordinates] = weather
        if not wild_weather_dict:
            return None
        weather_search = {k: (float(k.split(",")[0]), float(k.split(",")[1])) for k,v in wild_weather_dict.items()}
        dist = lambda s, key: (float(s[0]) - float(weather_search[key][0])) ** 2 + \
                              (float(s[1]) - float(weather_search[key][1])) ** 2
        nearest_wild = min(weather_search, key=functools.partial(dist, coord))
        return wild_weather_dict[nearest_wild]

    """
    Admin Commands
    """

    @tasks.loop(seconds=0)
    async def auto_raid_json(self):
        while True:
            try:
                to_midnight = 24*60*60 - ((datetime.datetime.utcnow()-datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)).seconds)
                to_sixam = 24*60*60 - ((datetime.datetime.utcnow()-datetime.datetime.utcnow().replace(hour=6, minute=0, second=0, microsecond=0)).seconds)
                to_noon = 24*60*60 - ((datetime.datetime.utcnow()-datetime.datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)).seconds)
                to_sixpm = 24*60*60 - ((datetime.datetime.utcnow()-datetime.datetime.utcnow().replace(hour=18, minute=0, second=0, microsecond=0)).seconds)
                try:
                    await asyncio.sleep(min([to_sixpm, to_sixam, to_midnight, to_noon]))
                except asyncio.CancelledError:
                    break
                tsr_bosses = []
                tsr_boss_dict = {}
                old_raid_dict = {}
                for raid_level in self.bot.raid_info['raid_eggs']:
                    old_raid_dict[raid_level] = self.bot.raid_info['raid_eggs'][raid_level]['pokemon']
                with open(os.path.join('data', 'raid_info.json'), 'r') as fd:
                    data = json.load(fd)
                async with aiohttp.ClientSession() as sess:
                    async with sess.get("https://thesilphroad.com/raid-bosses") as resp:
                        html = await resp.text()
                        for line in html.splitlines():
                            if "Raids</h4>" in line or "<h4>Tier" in line or "<div class=\"boss-name\">" in line:
                                tsr_bosses.append(line.strip())
                if tsr_bosses:
                    for index, item in enumerate(tsr_bosses):
                        tsr_bosses[index] = item.replace("<h4>", "").replace("</h4>", "").replace("<div class=\"boss-name\">", "").replace("</div>", "").replace("Raids", "").replace("Tier", "").strip()
                if tsr_bosses:
                    for item in tsr_bosses:
                        if item.isdigit() or item == "EX":
                            tsr_boss_dict[item] = []
                            current_list = tsr_boss_dict[item]
                        else:
                            current_list.append(item)
                for raid_level in tsr_boss_dict:
                    if not data['raid_eggs'][str(raid_level)].get('overwrites', {}):
                        continue
                    for overwrite in copy.deepcopy(data['raid_eggs'][str(raid_level)]['overwrites']):
                        if time.time() >= data['raid_eggs'][str(raid_level)]['overwrites'][overwrite]['replace_until']:
                            del data['raid_eggs'][str(raid_level)]['overwrites'][overwrite]
                    with open(os.path.join('data', 'raid_info.json'), 'w') as fd:
                        json.dump(data, fd, indent=2, separators=(', ', ': '))
                    for index, pokemon in enumerate(tsr_boss_dict[raid_level]):
                        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, pokemon)
                        if str(pokemon) in self.bot.raid_info['raid_eggs'][str(raid_level)].get('overwrites', {}):
                            replace_with = self.bot.raid_info['raid_eggs'][str(raid_level)]['overwrites'][str(pokemon)]['replace_with']
                            tsr_boss_dict[raid_level][index] = replace_with
                    tsr_boss_dict[raid_level] = [x for x in tsr_boss_dict[raid_level] if x]
                if tsr_boss_dict:
                    with open(os.path.join('data', 'raid_info.json'), 'r') as fd:
                        data = json.load(fd)
                    for raid_level in tsr_boss_dict:
                        data['raid_eggs'][raid_level]['pokemon'] = list(tsr_boss_dict[raid_level])
                    test = json.dumps(data)
                    json.loads(test)
                    data['last_edit'] = time.time()
                    new_raid_dict = copy.deepcopy(tsr_boss_dict)
                    with open(os.path.join('data', 'raid_info.json'), 'w') as fd:
                        json.dump(data, fd, indent=2, separators=(', ', ': '))
                    await pkmn_class.Pokedex.generate_lists(self.bot)
                    self.bot.raid_dict = await utils.get_raid_dict(self.bot)
                    self.bot.raid_list = list(itertools.chain.from_iterable(self.bot.raid_dict.values()))
                    for guild in list(self.bot.guilds):
                        for report_dict in self.bot.channel_report_dicts:
                            for channel_id in list(self.bot.guild_dict[guild.id].setdefault(report_dict, {}).keys()):
                                channel = self.bot.get_channel(channel_id)
                                for raid_level in new_raid_dict:
                                    if self.bot.guild_dict[guild.id][report_dict][channel.id]['egg_level'] == str(raid_level):
                                        for trainer_id in list(self.bot.guild_dict[guild.id][report_dict][channel.id]['trainer_dict'].keys()):
                                            interest = copy.copy(self.bot.guild_dict[guild.id][report_dict][channel.id]['trainer_dict'][trainer_id].get('interest', []))
                                            new_bosses = list(set(new_raid_dict[raid_level]) - set(old_raid_dict[raid_level]))
                                            new_bosses = [x.lower() for x in new_bosses]
                                            self.bot.guild_dict[guild.id][report_dict][channel.id]['trainer_dict'][trainer_id]['interest'] = [*interest, *new_bosses]
                                        self.bot.guild_dict[guild.id][report_dict][channel.id]['pkmn_obj'] = ''
                                        if self.bot.active_channels.get(channel.id, {}).get('pokemon'):
                                            self.bot.active_channels[channel.id]['pokemon'] = None
                                        self.bot.guild_dict[guild.id][report_dict][channel.id]['ctrs_dict'] = {}
                                        self.bot.guild_dict[guild.id][report_dict][channel.id]['ctrsmessage'] = None
                                        channel = self.bot.get_channel(channel.id)
                                        await self._edit_party(channel)
            except Exception as e:
                print(traceback.format_exc())

    @auto_raid_json.before_loop
    async def before_auto_raid_json(self):
        await self.bot.wait_until_ready()

    @commands.group(invoke_without_command=True, case_insensitive=True)
    @checks.is_manager()
    async def raid_json(self, ctx, level="", *, new_list=""):
        """Edits or displays raid_info.json

        Usage: !raid_json [level] [list]"""
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        raid_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/raid_tut_raid.png?cache=1')
        raid_embed.set_footer(text=_('Sent by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        def check(reply):
            if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                return True
            else:
                return False
        error = False
        first = True
        action = ""
        msg = ""
        edit_level = ""
        edit_list = []
        old_raid_dict = {}
        for raid_level in self.bot.raid_info['raid_eggs']:
            old_raid_dict[raid_level] = self.bot.raid_info['raid_eggs'][raid_level]['pokemon']
        if level.lower() == "list" and not new_list:
            return await ctx.invoke(self.bot.get_command('raid_json list'))
        elif level.lower() == "tsr" or new_list.lower() == "tsr" or action == "tsr":
            return await ctx.invoke(self.bot.get_command('raid_json tsr'))
        elif (level.isdigit() and level in self.bot.raid_info['raid_eggs']) or level.lower() == "ex":
            edit_level = level.lower()
            if new_list.lower() == "list":
                return await ctx.invoke(self.bot.get_command('raid_json list'), level=edit_level)
            elif new_list.lower() == "overwrite":
                return await ctx.invoke(self.bot.get_command('raid_json overwrite'), level=edit_level)
            else:
                edit_list = new_list.split(',')
                edit_list = [x.strip() for x in edit_list]
                edit_list = [re.sub('[^a-zA-Z0-9 ]' , '' , x) for x in edit_list]
                edit_list = [await pkmn_class.Pokemon.async_get_pokemon(self.bot, x) for x in edit_list]
                edit_list = [x for x in edit_list if x]
        while True:
            async with ctx.typing():
                if not edit_level:
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**Edit Raid Bosses**'), value=f"{'Meowth! I will help you edit raid bosses!' if first else ''}\n\n{'First' if first else 'Meowth! Now'}, I'll need to know what **level** of bosses you'd like to modify. Reply with **1, 2, 3, 4, 5, or EX**. Or, if you want to list all bosses, reply with **list**. You can reply with **cancel** to stop anytime.\n\nAlternatively, reply with **tsr** to attempt to pull data from TSR's raid boss list.", inline=False)
                    boss_level_wait = await channel.send(embed=raid_embed)
                    try:
                        boss_level_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        boss_level_msg = None
                    await utils.safe_delete(boss_level_wait)
                    if not boss_level_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(boss_level_msg)
                    if boss_level_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif boss_level_msg.clean_content.lower() == "list":
                        return await ctx.invoke(self.bot.get_command('raid_json list'))
                    elif boss_level_msg.clean_content.lower() == "tsr":
                        return await ctx.invoke(self.bot.get_command('raid_json tsr'))
                    elif not any([boss_level_msg.clean_content.lower() == "ex", boss_level_msg.clean_content.isdigit()]):
                        error = _("entered an invalid option")
                        break
                    elif boss_level_msg.clean_content not in self.bot.raid_info['raid_eggs']:
                        error = _("entered an invalid level")
                        break
                    else:
                        edit_level = boss_level_msg.clean_content.lower()
                    first = False
                if not edit_list:
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**Edit Raid Bosses**'), value=f"{'Meowth! I will help you edit raid bosses!' if first else ''}\n\n{'First' if first else 'Meowth! Now'}, I'll need to know what **bosses** you'd like to set for level {edit_level} raids. Reply with a comma separated list of bosses including any forms. Or, if you want to list all bosses in level {edit_level} raids, reply with **list**.\n\nAlternatively, if TSR is giving incorrect forms or gives unwanted upcoming pokemon, you can overwrite using **overwrite**. \n\nYou can reply with **cancel** to stop anytime.", inline=False)
                    boss_list_wait = await channel.send(embed=raid_embed)
                    try:
                        boss_list_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        boss_list_msg = None
                    await utils.safe_delete(boss_list_wait)
                    if not boss_list_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(boss_list_msg)
                    if boss_list_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif boss_list_msg.clean_content.lower() == "list":
                        return await ctx.invoke(self.bot.get_command('raid_json list'), level=edit_level)
                    elif boss_list_msg.clean_content.lower() == "overwrite":
                        return await ctx.invoke(self.bot.get_command('raid_json overwrite'), level=edit_level)
                    else:
                        new_list = re.sub(r'\[|\]|\'|\"', '', str(boss_list_msg.clean_content.lower())).split(',')
                        edit_list = [x.strip() for x in new_list]
                        edit_list = [re.sub('[^a-zA-Z0-9 ]' , '' , x) for x in edit_list]
                        edit_list = [await pkmn_class.Pokemon.async_get_pokemon(self.bot, x) for x in edit_list]
                        edit_list = [x for x in edit_list if x]
                        if not edit_list:
                            error = _("didn't enter any pokemon")
                            break
                    first = False
                if edit_level and edit_list:
                    for pokemon in edit_list:
                        pokemon.shiny = False
                        pokemon.gender = False
                        pokemon.size = False
                        pokemon.shadow = False
                    msg += _('I will replace this:\n')
                    msg += _('**Level {level} boss list:**\n`{raidlist}` \n').format(level=edit_level, raidlist=self.bot.raid_info['raid_eggs'][edit_level]['pokemon'])
                    msg += _('\nWith this:\n')
                    msg += _('**Level {level} boss list:**\n`{raidlist}` \n').format(level=edit_level, raidlist=[str(x) for x in edit_list])
                    msg += _('\nWould you like to continue?')
                    raid_embed.clear_fields()
                    raid_embed.add_field(name="Raid Boss Edit", value=msg)
                    question = await ctx.channel.send(embed=raid_embed)
                    try:
                        timeout = False
                        res, reactuser = await utils.ask(self.bot, question, ctx.author.id)
                    except TypeError:
                        timeout = True
                    if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', u'\U0000274e'):
                        await utils.safe_delete(question)
                        error = _('cancelled the command')
                    elif res.emoji == self.bot.custom_emoji.get('answer_yes', u'\U00002705'):
                        pass
                    else:
                        error = _('did something invalid')
                    await utils.safe_delete(question)
                    break
        if error:
            raid_embed.clear_fields()
            raid_embed.add_field(name=_('**Boss Edit Cancelled**'), value=_("Meowth! Your edit has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=raid_embed, delete_after=10)
            await utils.safe_delete(message)
        else:
            raid_embed.clear_fields()
            raid_embed.add_field(name=_('**Boss Edit Completed**'), value=_("Meowth! Your edit completed successfully.").format(error=error), inline=False)
            confirmation = await channel.send(embed=raid_embed)
            with open(os.path.join('data', 'raid_info.json'), 'r') as fd:
                data = json.load(fd)
            tmp = data['raid_eggs'][edit_level]['pokemon']
            edit_list = [str(x) for x in edit_list if x]
            data['raid_eggs'][edit_level]['pokemon'] = edit_list
            data['last_edit'] = time.time()
            new_raid_dict = {edit_level: edit_list}
            with open(os.path.join('data', 'raid_info.json'), 'w') as fd:
                json.dump(data, fd, indent=2, separators=(', ', ': '))
            await pkmn_class.Pokedex.generate_lists(self.bot)
            self.bot.raid_dict = await utils.get_raid_dict(self.bot)
            self.bot.raid_list = list(itertools.chain.from_iterable(self.bot.raid_dict.values()))
            for guild in list(self.bot.guilds):
                for report_dict in self.bot.channel_report_dicts:
                    for channel_id in list(self.bot.guild_dict[guild.id].setdefault(report_dict, {}).keys()):
                        channel = self.bot.get_channel(channel_id)
                        for raid_level in new_raid_dict:
                            if self.bot.guild_dict[guild.id][report_dict][channel.id]['egg_level'] == str(raid_level):
                                for trainer_id in list(self.bot.guild_dict[guild.id][report_dict][channel.id]['trainer_dict'].keys()):
                                    interest = copy.copy(self.bot.guild_dict[guild.id][report_dict][channel.id]['trainer_dict'][trainer_id].get('interest', []))
                                    new_bosses = list(set(new_raid_dict[raid_level]) - set(old_raid_dict[raid_level]))
                                    new_bosses = [x.lower() for x in new_bosses]
                                    self.bot.guild_dict[guild.id][report_dict][channel.id]['trainer_dict'][trainer_id]['interest'] = [*interest, *new_bosses]
                                self.bot.guild_dict[guild.id][report_dict][channel.id]['pkmn_obj'] = ''
                                if self.bot.active_channels.get(channel.id, {}).get('pokemon'):
                                    self.bot.active_channels[channel.id]['pokemon'] = None
                                self.bot.guild_dict[guild.id][report_dict][channel.id]['ctrs_dict'] = {}
                                self.bot.guild_dict[guild.id][report_dict][channel.id]['ctrsmessage'] = None
                                channel = self.bot.get_channel(channel.id)
                                await self._edit_party(channel)
            await utils.safe_delete(message)

    @raid_json.command(name="list", hidden=True)
    @checks.is_manager()
    async def raid_json_list(self, ctx, level=None):
        raid_embed = discord.Embed(colour=ctx.message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/raid_tut_raid.png?cache=1')
        if self.bot.raid_info.get('last_edit', False):
            last_edit = datetime.datetime.utcfromtimestamp(self.bot.raid_info['last_edit']) + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
            raid_embed.set_footer(text=f"Last Update: {last_edit.strftime('%B %d at %I:%M %p')}")
        msg = ""
        if not level:
            for raid_level in self.bot.raid_info['raid_eggs']:
                msg += _('\n**Level {level} bosses:**\n`{raidlist}` \n').format(level=raid_level, raidlist=self.bot.raid_info['raid_eggs'][raid_level]['pokemon'])
            raid_embed.add_field(name="Raid Boss List", value=msg)
            return await ctx.channel.send(embed=raid_embed)
        elif (level.isdigit() and level in self.bot.raid_info['raid_eggs']) or level.lower() == "ex":
            msg = _('**Level {level} bosses:**\n`{raidlist}` \n').format(level=level, raidlist=self.bot.raid_info['raid_eggs'][level]['pokemon'])
            raid_embed.add_field(name="Raid Boss List", value=msg)
            return await ctx.channel.send(embed=raid_embed)

    @raid_json.command(name="tsr", hidden=True)
    @checks.is_manager()
    async def raid_json_tsr(self, ctx):
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        raid_embed = discord.Embed(colour=ctx.message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/raid_tut_raid.png?cache=1')
        raid_embed.set_footer(text=_('Sent by @{author} - {timestamp}').format(author=ctx.author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=ctx.author.avatar_url_as(format=None, static_format='jpg', size=32))
        tsr_bosses = []
        tsr_boss_dict = {}
        msg = ""
        old_raid_dict = {}
        for raid_level in self.bot.raid_info['raid_eggs']:
            old_raid_dict[raid_level] = self.bot.raid_info['raid_eggs'][raid_level]['pokemon']
        async with ctx.typing():
            with open(os.path.join('data', 'raid_info.json'), 'r') as fd:
                data = json.load(fd)
            async with aiohttp.ClientSession() as sess:
                async with sess.get("https://thesilphroad.com/raid-bosses") as resp:
                    html = await resp.text()
                    for line in html.splitlines():
                        if "Raids</h4>" in line or "<h4>Tier" in line or "<div class=\"boss-name\">" in line:
                            tsr_bosses.append(line.strip())
            if tsr_bosses:
                for index, item in enumerate(tsr_bosses):
                    tsr_bosses[index] = item.replace("<h4>", "").replace("</h4>", "").replace("<div class=\"boss-name\">", "").replace("</div>", "").replace("Raids", "").replace("Tier", "").strip()
            if tsr_bosses:
                for item in tsr_bosses:
                    if item.isdigit() or item == "EX":
                        tsr_boss_dict[item] = []
                        current_list = tsr_boss_dict[item]
                    else:
                        current_list.append(item)
            for raid_level in tsr_boss_dict:
                if not data['raid_eggs'][str(raid_level)].get('overwrites', {}):
                    continue
                for overwrite in copy.deepcopy(data['raid_eggs'][str(raid_level)]['overwrites']):
                    if time.time() >= data['raid_eggs'][str(raid_level)]['overwrites'][overwrite]['replace_until']:
                        del data['raid_eggs'][str(raid_level)]['overwrites'][overwrite]
                with open(os.path.join('data', 'raid_info.json'), 'w') as fd:
                    json.dump(data, fd, indent=2, separators=(', ', ': '))
                for index, pokemon in enumerate(tsr_boss_dict[raid_level]):
                    pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, pokemon)
                    if str(pokemon) in self.bot.raid_info['raid_eggs'][str(raid_level)].get('overwrites', {}):
                        replace_with = self.bot.raid_info['raid_eggs'][str(raid_level)]['overwrites'][str(pokemon)]['replace_with']
                        tsr_boss_dict[raid_level][index] = replace_with
                tsr_boss_dict[raid_level] = [x for x in tsr_boss_dict[raid_level] if x]
            if tsr_boss_dict:
                msg += _('I will replace this:\n')
                for raid_level in tsr_boss_dict:
                    msg += f"**Level {raid_level} boss list:**\n`{self.bot.raid_info['raid_eggs'][raid_level]['pokemon']}` \n"
                raid_embed.clear_fields()
                raid_embed.add_field(name="Raid Boss Edit", value=msg)
                question1 = await ctx.channel.send(embed=raid_embed, delete_after=60)
                msg = _('\nWith this:\n')
                for raid_level in tsr_boss_dict:
                    msg += f"**Level {raid_level} boss list:**\n`{tsr_boss_dict[raid_level]}` \n"
                msg += f"\nWould you like to continue? If this doesn't look correct, remember there may be overwrites in **{ctx.prefix}raid_json overwrite**"
                raid_embed.clear_fields()
                raid_embed.add_field(name="Raid Boss Edit", value=msg)
                question2 = await ctx.channel.send(embed=raid_embed)
                try:
                    timeout = False
                    res, reactuser = await utils.ask(self.bot, question2, ctx.author.id)
                except TypeError:
                    timeout = True
                await utils.safe_bulk_delete(ctx.channel, [question1, question2])
                if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', u'\U0000274e'):
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**Boss Edit Cancelled**'), value=_("Meowth! Your edit has been cancelled because you cancelled the command! Retry when you're ready."), inline=False)
                    return await ctx.send(embed=raid_embed, delete_after=10)
                elif res.emoji == self.bot.custom_emoji.get('answer_yes', u'\U00002705'):
                    with open(os.path.join('data', 'raid_info.json'), 'r') as fd:
                        data = json.load(fd)
                    for raid_level in tsr_boss_dict:
                        data['raid_eggs'][raid_level]['pokemon'] = list(tsr_boss_dict[raid_level])
                    try:
                        test = json.dumps(data)
                        json.loads(test)
                    except:
                        raid_embed.clear_fields()
                        raid_embed.add_field(name=_('**Boss Edit Cancelled**'), value=_("Meowth! Your edit has been cancelled because TSR didn't respond correctly! Retry when you're ready."), inline=False)
                        return await ctx.send(embed=raid_embed, delete_after=10)
                    data['last_edit'] = time.time()
                    with open(os.path.join('data', 'raid_info.json'), 'w') as fd:
                        json.dump(data, fd, indent=2, separators=(', ', ': '))
                    await pkmn_class.Pokedex.generate_lists(self.bot)
                    self.bot.raid_dict = await utils.get_raid_dict(self.bot)
                    self.bot.raid_list = list(itertools.chain.from_iterable(self.bot.raid_dict.values()))
                    for guild in list(self.bot.guilds):
                        for report_dict in self.bot.channel_report_dicts:
                            for channel_id in list(self.bot.guild_dict[guild.id].setdefault(report_dict, {}).keys()):
                                channel = self.bot.get_channel(channel_id)
                                for raid_level in tsr_boss_dict:
                                    if self.bot.guild_dict[guild.id][report_dict][channel.id]['egg_level'] == str(raid_level):
                                        for trainer_id in list(self.bot.guild_dict[guild.id][report_dict][channel.id]['trainer_dict'].keys()):
                                            interest = copy.copy(self.bot.guild_dict[guild.id][report_dict][channel.id]['trainer_dict'][trainer_id].get('interest', []))
                                            new_bosses = list(set(tsr_boss_dict[raid_level]) - set(old_raid_dict[raid_level]))
                                            new_bosses = [x.lower() for x in new_bosses]
                                            self.bot.guild_dict[guild.id][report_dict][channel.id]['trainer_dict'][trainer_id]['interest'] = [*interest, *new_bosses]
                                        self.bot.guild_dict[guild.id][report_dict][channel.id]['pkmn_obj'] = ''
                                        if self.bot.active_channels.get(channel.id, {}).get('pokemon'):
                                            self.bot.active_channels[channel.id]['pokemon'] = None
                                        self.bot.guild_dict[guild.id][report_dict][channel.id]['ctrs_dict'] = {}
                                        self.bot.guild_dict[guild.id][report_dict][channel.id]['ctrsmessage'] = None
                                        channel = self.bot.get_channel(channel.id)
                                        await self._edit_party(channel)
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**Boss Edit Successful**'), value=_("Meowth! Your edit was successful!."), inline=False)
                    return await ctx.send(embed=raid_embed, delete_after=10)
                else:
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**Boss Edit Cancelled**'), value=_("Meowth! Your edit has been cancelled because you did something invalid! Retry when you're ready."), inline=False)
                    return await ctx.send(embed=raid_embed, delete_after=10)

    @raid_json.command(name="overwrite", hidden=True)
    @checks.is_manager()
    async def raid_json_overwrite(self, ctx, level=""):
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        raid_embed = discord.Embed(colour=ctx.message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/raid_tut_raid.png?cache=1')
        def check(reply):
            if reply.author is not ctx.guild.me and reply.channel.id == ctx.channel.id and reply.author == ctx.author:
                return True
            else:
                return False
        if (level.isdigit() and level in self.bot.raid_info['raid_eggs']) or level.lower() == "ex":
            level = level.upper()
        if not level:
            raid_embed.clear_fields()
            raid_embed.add_field(name=_('**Edit Raid Overwrites**'), value=f"Meowth! I will help you edit raid boss overwrites! First, I'll need to know what **level** of bosses you'd like to overwrite. Reply with **1, 2, 3, 4, 5, or EX**. You can reply with **cancel** to stop anytime.", inline=False)
            boss_level_wait = await ctx.send(embed=raid_embed)
            try:
                boss_level_msg = await self.bot.wait_for('message', timeout=60, check=check)
            except asyncio.TimeoutError:
                boss_level_msg = None
            await utils.safe_delete(boss_level_wait)
            if not boss_level_msg:
                raid_embed.clear_fields()
                raid_embed.add_field(name=_('**Boss Overwrite Cancelled**'), value=_("Meowth! Your edit has been cancelled because you took too long to respond! Retry when you're ready."), inline=False)
                return await ctx.send(embed=raid_embed, delete_after=10)
            else:
                await utils.safe_delete(boss_level_msg)
            if boss_level_msg.clean_content.lower() == "cancel":
                raid_embed.clear_fields()
                raid_embed.add_field(name=_('**Boss Overwrite Cancelled**'), value=_("Meowth! Your edit has been cancelled because you cancelled the report! Retry when you're ready."), inline=False)
                return await ctx.send(embed=raid_embed, delete_after=10)
            elif boss_level_msg.clean_content.lower() == "list":
                return await ctx.invoke(self.bot.get_command('raid_json list'))
            elif boss_level_msg.clean_content.lower() == "tsr":
                return await ctx.invoke(self.bot.get_command('raid_json tsr'))
            elif not any([boss_level_msg.clean_content.lower() == "ex", boss_level_msg.clean_content.isdigit()]):
                raid_embed.clear_fields()
                raid_embed.add_field(name=_('**Boss Overwrite Cancelled**'), value=_("Meowth! Your edit has been cancelled because you entered an invalid option! Retry when you're ready."), inline=False)
                return await ctx.send(embed=raid_embed, delete_after=10)
            elif boss_level_msg.clean_content not in self.bot.raid_info['raid_eggs']:
                raid_embed.clear_fields()
                raid_embed.add_field(name=_('**Boss Overwrite Cancelled**'), value=_("Meowth! Your edit has been cancelled because you entered an invalid level! Retry when you're ready."), inline=False)
                return await ctx.send(embed=raid_embed, delete_after=10)
            else:
                level = boss_level_msg.clean_content.lower()
        current_overwrites = self.bot.raid_info['raid_eggs'][level].get('overwrites', {})
        raid_embed.clear_fields()
        raid_embed.add_field(name=f"**Current Boss Overwrites**", value=f"")
        overwrite_str = ""
        for overwrite in current_overwrites:
            if len(overwrite_str) < 1000:
                overwrite_str += f"{overwrite} = {current_overwrites[overwrite]['replace_with']}\n"
                raid_embed.set_field_at(0, name=f"**Current Boss Overwrites**", value=overwrite_str)
            else:
                await ctx.send(embed=raid_embed, delete_after=60)
                overwrite_str += f"{overwrite} = {current_overwrites[overwrite]['replace_with']}\n"
        if current_overwrites:
            await ctx.send(embed=raid_embed, delete_after=60)
        new_overwrites = {}
        raid_embed.clear_fields()
        raid_embed.set_footer(text=_('Sent by @{author} - {timestamp}').format(author=ctx.author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=ctx.author.avatar_url_as(format=None, static_format='jpg', size=32))
        raid_embed.add_field(name=_('**Edit Raid Overwrtes**'), value=f"Meowth! I will help you edit raid boss overwrites! This is useful if TSR doesn't include a form for a pokemon, or is sending upcoming pokemon, or something similar.\n\nYou are changing overwrites of level {level} raids. {'The current list is listed above.' if current_overwrites else 'You have no current boss overwrites.'}\n\nThe correct format for this is:\n`Incorrect Pokemon = Correct Pokemon, Incorrect Pokemon=Correct Pokemon, Unwanted Pokemon=None`\n\nReply with any overwrites to add to my current list, **none** to remove all overwrites for level {level} raids, or **cancel** to stop anytime.", inline=False)
        boss_list_wait = await ctx.send(embed=raid_embed)
        try:
            boss_list_msg = await self.bot.wait_for('message', timeout=60, check=check)
        except asyncio.TimeoutError:
            boss_list_msg = None
        await utils.safe_delete(boss_list_wait)
        if not boss_list_msg:
            raid_embed.clear_fields()
            raid_embed.add_field(name=_('**Boss Overwrite Cancelled**'), value=_("Meowth! Your edit has been cancelled because you took too long to respond! Retry when you're ready."), inline=False)
            return await ctx.send(embed=raid_embed, delete_after=10)
        else:
            await utils.safe_delete(boss_list_msg)
        if boss_list_msg.clean_content.lower() == "cancel":
            raid_embed.clear_fields()
            raid_embed.add_field(name=_('**Boss Overwrite Cancelled**'), value=_("Meowth! Your edit has been cancelled because you canceled the report! Retry when you're ready."), inline=False)
            return await ctx.send(embed=raid_embed, delete_after=10)
        elif boss_list_msg.clean_content.lower() == "none":
            new_overwrites = {}
        else:
            overwrite_list = boss_list_msg.clean_content.split(',')
            overwrite_list = [x.strip() for x in overwrite_list]
            for overwrite in overwrite_list:
                if len(overwrite.split('=')) != 2:
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**Boss Overwrite Cancelled**'), value=_("Meowth! Your edit has been cancelled because you entered an incorrect format! Retry when you're ready."), inline=False)
                    return await ctx.send(embed=raid_embed, delete_after=10)
                to_replace = await pkmn_class.Pokemon.async_get_pokemon(self.bot, overwrite.split('=')[0].strip())
                replace_with = await pkmn_class.Pokemon.async_get_pokemon(self.bot, overwrite.split('=')[1].strip())
                if not to_replace:
                    continue
                raid_embed.clear_fields()
                raid_embed.add_field(name=_('**Edit Raid Overwrtes**'), value=f"Meowth! Now, when do you want me to stop overwriting {str(to_replace)} with {str(replace_with)}? Is it part of an event with an end date or an upcoming event with a start date? Reply with a date and time for the following overwrite:\n\n**{str(to_replace)} = {str(replace_with)}**", inline=False)
                boss_time_wait = await ctx.send(embed=raid_embed)
                try:
                    boss_time_msg = await self.bot.wait_for('message', timeout=60, check=check)
                except asyncio.TimeoutError:
                    boss_time_msg = None
                await utils.safe_delete(boss_time_wait)
                if not boss_time_msg:
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**Boss Overwrite Cancelled**'), value=_("Meowth! Your edit has been cancelled because you took too long to respond! Retry when you're ready."), inline=False)
                    return await ctx.send(embed=raid_embed, delete_after=10)
                else:
                    await utils.safe_delete(boss_time_msg)
                if boss_time_msg.clean_content.lower() == "cancel":
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**Boss Overwrite Cancelled**'), value=_("Meowth! Your edit has been cancelled because you canceled the request! Retry when you're ready."), inline=False)
                    return await ctx.send(embed=raid_embed, delete_after=10)
                else:
                    replace_until = dateparser.parse(boss_time_msg.clean_content, settings={'DATE_ORDER': 'MDY', 'RETURN_AS_TIMEZONE_AWARE': False})
                    replace_until = replace_until - datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                    replace_until = replace_until - datetime.timedelta(hours=6)
                if replace_with:
                    new_overwrites[str(to_replace)] = {"replace_with":str(replace_with), "replace_until":replace_until.replace(tzinfo=datetime.timezone.utc).timestamp()}
                else:
                    new_overwrites[str(to_replace)] = {"replace_with":"", "replace_until":replace_until.replace(tzinfo=datetime.timezone.utc).timestamp()}
        if new_overwrites or boss_list_msg.clean_content.lower() == "none":
            with open(os.path.join('data', 'raid_info.json'), 'r') as fd:
                data = json.load(fd)
            if boss_list_msg.clean_content.lower() == "none":
                data['raid_eggs'][level]['overwrites'] = {}
            else:
                data['raid_eggs'][level]['overwrites'] = {**current_overwrites, **new_overwrites}
            with open(os.path.join('data', 'raid_info.json'), 'w') as fd:
                json.dump(data, fd, indent=2, separators=(', ', ': '))
            raid_embed.clear_fields()
            raid_embed.add_field(name=_('**Boss Overwrite Successful**'), value=_("Meowth! Your overwrites were successful!"), inline=False)
            return await ctx.send(embed=raid_embed, delete_after=10)

    @commands.command()
    @checks.is_manager()
    async def raid_time(self, ctx, hatch_or_raid=None, level=None, new_time=None):
        """Edits raid time in raid_info.json

        Usage: !raid_time [hatch_or_raid] [level] [new_time]
        hatch_or_raid = input the word hatch or raid to set which time to change
        level = 1 through 5 or all
        new_time = new time to change to in minutes"""
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        error = False
        first = True
        msg = ""
        raid_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/raid_tut_raid.png?cache=1')
        raid_embed.set_footer(text=_('Sent by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        def check(reply):
            if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                return True
            else:
                return False
        while True:
            async with ctx.typing():
                edit_type = None
                if hatch_or_raid and hatch_or_raid.lower() == "hatch":
                    edit_type = "hatchtime"
                elif hatch_or_raid and hatch_or_raid.lower() == "raid":
                    edit_type = "raidtime"
                if not edit_type:
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**Edit Raid Times**'), value=f"{'Meowth! I will help you edit raid times!' if first else ''}\n\n{'First' if first else 'Meowth! Now'}, I'll need to know what **time** you'd like to edit. Reply with **hatch** or **raid**. You can reply with **cancel** to stop anytime.", inline=False)
                    time_type_wait = await channel.send(embed=raid_embed)
                    try:
                        time_type_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        time_type_msg = None
                    await utils.safe_delete(time_type_wait)
                    if not time_type_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(time_type_msg)
                    if time_type_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif not any([time_type_msg.clean_content.lower() == "hatch", time_type_msg.clean_content.lower() == "raid"]):
                        error = _("entered something invalid")
                        break
                    else:
                        edit_type = f"{time_type_msg.clean_content.lower()}time"
                    first = False
                edit_level = None
                if level and level.lower() == "ex":
                    edit_level = "EX"
                elif level and level in self.bot.raid_info['raid_eggs']:
                    edit_level = level
                if not edit_level:
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**Edit Raid Times**'), value=f"{'Meowth! I will help you edit raid times!' if first else ''}\n\n{'First' if first else 'Meowth! Now'}, I'll need to know what **level** of times you'd like to modify. Reply with **1, 2, 3, 4, 5, EX, or all**. You can reply with **cancel** to stop anytime.", inline=False)
                    time_level_wait = await channel.send(embed=raid_embed)
                    try:
                        time_level_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        time_level_msg = None
                    await utils.safe_delete(time_level_wait)
                    if not time_level_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(time_level_msg)
                    if time_level_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif not any([time_level_msg.clean_content.lower() == "ex", time_level_msg.clean_content.lower() == "all", time_level_msg.clean_content.isdigit()]):
                        error = _("entered an invalid option")
                        break
                    elif time_level_msg.clean_content not in self.bot.raid_info['raid_eggs'] and time_level_msg.clean_content.lower() != "all":
                        error = _("entered an invalid level")
                        break
                    else:
                        edit_level = time_level_msg.clean_content.lower()
                    first = False
                edit_time = None
                if new_time and new_time.isdigit():
                    edit_time = int(new_time)
                if not edit_time:
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**Edit Raid Bosses**'), value=f"{'Meowth! I will help you edit raid times!' if first else ''}\n\n{'First' if first else 'Meowth! Now'}, I'll need to know what the **new time** for level {edit_level} raid {edit_type.replace('time', ' time')}. Reply with a new time. You can reply with **cancel** to stop anytime.", inline=False)
                    boss_list_wait = await channel.send(embed=raid_embed)
                    try:
                        boss_list_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        boss_list_msg = None
                    await utils.safe_delete(boss_list_wait)
                    if not boss_list_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(boss_list_msg)
                    if boss_list_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif not boss_list_msg.clean_content.isdigit():
                        error = _("didn't enter a number")
                        break
                    else:
                        edit_time = int(boss_list_msg.clean_content.lower())
                    first = False
                if edit_level and edit_time and edit_type:
                    if edit_level == "all":
                        msg += _('I will change all **{hatch_or_raid}** times to **{newtime}** minutes.').format(hatch_or_raid=edit_type.replace('time', ''), newtime=edit_time)
                    else:
                        msg += _('I will change Level **{level}**\'s **{hatch_or_raid}** time from **{oldtime}** minutes to **{newtime}** minutes.').format(level=edit_level, hatch_or_raid=edit_type.replace('time', ''), oldtime=self.bot.raid_info['raid_eggs'][edit_level][edit_type], newtime=edit_time)
                    msg += _('\nWould you like to continue?')
                    raid_embed.clear_fields()
                    raid_embed.add_field(name="Raid Boss Edit", value=msg)
                    question = await ctx.channel.send(embed=raid_embed)
                    try:
                        timeout = False
                        res, reactuser = await utils.ask(self.bot, question, ctx.author.id)
                    except TypeError:
                        timeout = True
                    if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', u'\U0000274e'):
                        await utils.safe_delete(question)
                        error = _('cancelled the command')
                        break
                    elif res.emoji == self.bot.custom_emoji.get('answer_yes', u'\U00002705'):
                        pass
                    else:
                        error = _('did something invalid')
                        break
                    await utils.safe_delete(question)
                    break
        if error:
            raid_embed.clear_fields()
            raid_embed.add_field(name=_('**Time Edit Cancelled**'), value=_("Meowth! Your edit has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=raid_embed, delete_after=10)
            await utils.safe_delete(message)
        else:
            raid_embed.clear_fields()
            raid_embed.add_field(name=_('**Time Edit Completed**'), value=_("Meowth! Your edit completed successfully.").format(error=error), inline=False)
            confirmation = await channel.send(embed=raid_embed, delete_after=90)
            with open(os.path.join('data', 'raid_info.json'), 'r') as fd:
                data = json.load(fd)
            if edit_level.lower() == "all":
                levellist = ["1", "2", "3", "4", "5"]
                for level in levellist:
                    tmp = data['raid_eggs'][level][edit_type]
                    data['raid_eggs'][level][edit_type] = int(edit_time)
                    with open(os.path.join('data', 'raid_info.json'), 'w') as fd:
                        json.dump(data, fd, indent=2, separators=(', ', ': '))
            else:
                tmp = data['raid_eggs'][edit_level][edit_type]
                data['raid_eggs'][edit_level][edit_type] = int(edit_time)
                with open(os.path.join('data', 'raid_info.json'), 'w') as fd:
                    json.dump(data, fd, indent=2, separators=(', ', ': '))
            await utils.safe_delete(message)

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    @checks.raidchannel()
    async def unassume(self, ctx):
        "Use if a level 5 egg assumed before you changed raid_json"
        report_dict = await utils.get_report_dict(ctx.bot, ctx.channel)
        try:
            ctrs_message = await ctx.channel.fetch_message(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['ctrsmessage'])
            await utils.safe_delete(ctrs_message)
        except:
            pass
        if not self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['pkmn_obj']:
            return await ctx.send("This channel hasn't been assumed", delete_after=10)
        egg_level = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['egg_level']
        if egg_level == '0':
            return await ctx.send("This channel has already hatched.", delete_after=10)
        boss_list = []
        for boss in self.bot.raid_dict[egg_level]:
            if isinstance(boss, pkmn_class.Pokemon):
                boss_list.append(str(boss).lower())
        for trainer in self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['trainer_dict']:
            self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['trainer_dict'][trainer]['interest'] = boss_list
        self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['pkmn_obj'] = ''
        if self.bot.active_channels.get(channel.id, {}).get('pokemon'):
            self.bot.active_channels[channel.id]['pokemon'] = None
        self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['pokemon'] = ''
        self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['ctrs_dict'] = {}
        self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['ctrsmessage'] = None
        await self._edit_party(ctx.channel)
        return await ctx.send("Channel successfully un-assumed", delete_after=10)

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    @checks.raidchannel()
    async def changeraid(self, ctx, *, newraid):
        """Changes raid boss.

        Usage: !changeraid <new pokemon or level>
        Only usable by admins."""
        message = ctx.message
        guild = message.guild
        channel = message.channel
        report_dict = await utils.get_report_dict(ctx.bot, ctx.channel)
        if (not channel) or (channel.id not in self.bot.guild_dict[guild.id][report_dict]) or ('raidchannel' not in str(report_dict)):
            return await channel.send(_('The channel you entered is not a raid channel.'), delete_after=10)
        if checks.check_exraidchannel(ctx) and newraid.isdigit():
            return await ctx.send('EX raids cannot be changed into regular raids. Please report separately.', delete_after=10)
        elif checks.check_exraidchannel(ctx) and newraid:
            egg_level = utils.get_level(self.bot, newraid)
            if egg_level != "EX" and newraid.lower() != "ex":
                return await ctx.send('EX raids cannot be changed into regular raids. Please report separately.', delete_after=10)
        if (checks.check_exraidchannel(ctx) and newraid.lower() == "ex") or newraid.isdigit():
            if checks.check_exraidchannel(ctx):
                newraid = "EX"
                self.bot.guild_dict[guild.id][report_dict][channel.id]['egg_level'] = "EX"
            elif newraid.isdigit():
                self.bot.guild_dict[guild.id][report_dict][channel.id]['egg_level'] = newraid
            address = self.bot.guild_dict[guild.id][report_dict][channel.id]['address']
            coordinates = self.bot.guild_dict[guild.id][report_dict][channel.id].get('coordinates', None)
            raidexp = self.bot.guild_dict[guild.id][report_dict][channel.id]['exp'] - time.time()
            report_channel = self.bot.get_channel(self.bot.guild_dict[guild.id][report_dict][channel.id]['report_channel'])
            report_author = ctx.guild.get_member(self.bot.guild_dict[guild.id][report_dict][channel.id]['report_author'])
            self.bot.guild_dict[guild.id][report_dict][channel.id]['pkmn_obj'] = ''
            if self.bot.active_channels.get(channel.id, {}).get('pokemon'):
                self.bot.active_channels[channel.id]['pokemon'] = None
            self.bot.guild_dict[guild.id][report_dict][channel.id]['type'] = 'egg'
            report_details = {
                'address':address,
                'coordinates':coordinates,
                'egg_level':newraid
            }
            raid_message = await channel.fetch_message(self.bot.guild_dict[guild.id][report_dict][channel.id]['raid_message'])
            report_message = await report_channel.fetch_message(self.bot.guild_dict[guild.id][report_dict][channel.id]['raid_report'])
            raid_embed = await self.make_raid_embed(ctx, report_details, raidexp)
            oldembed = raid_message.embeds[0]
            for field in oldembed.fields:
                if _('list') in field.name.lower():
                    raid_embed.add_field(name=field.name, value=field.value, inline=field.inline)
            content = raid_message.content.splitlines()
            content[0] = f"Meowth! Level {newraid} raid egg reported by {report_author.mention} in {report_channel.mention}! Details: {address}. Coordinate here!"
            raid_message.content = '\n'.join(content)
            report_message.content = '\n'.join(content).replace(f" in {report_channel.mention}", "").replace("Coordinate here!", f"Coordinate in {ctx.channel.mention}").replace(f"{content[-1]}", "")
            await raid_message.edit(new_content=raid_message.content, embed=raid_embed, content=raid_message.content)
            try:
                await report_message.edit(new_content=report_message.content, embed=raid_embed, content=report_message.content)
            except (discord.errors.NotFound, AttributeError):
                pass
            raid_channel_name = await self.edit_channel_name(channel)
            await channel.edit(name=raid_channel_name)
            if len(self.bot.raid_info['raid_eggs'][newraid]['pokemon']) == 1:
                await self._eggassume(ctx, self.bot.raid_info['raid_eggs'][newraid]['pokemon'][0], channel)
        elif newraid and not newraid.isdigit():
            egg_level = self.bot.guild_dict[guild.id][report_dict][channel.id]['egg_level']
            ctrs_message = self.bot.guild_dict[guild.id][report_dict][channel.id].setdefault('ctrsmessage', None)
            ctrs_dict = self.bot.guild_dict[guild.id][report_dict][channel.id].setdefault('ctrs_dict', {})
            pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, newraid)
            if not pokemon:
                return await ctx.send('Invalid pokemon', delete_after=10)
            if ctrs_message:
                try:
                    ctrs_message = await ctx.channel.fetch_message(ctrs_message)
                    await ctrs_message.delete()
                except:
                    pass
                self.bot.guild_dict[guild.id][report_dict][channel.id]['ctrsmessage'] = None
                self.bot.guild_dict[guild.id][report_dict][channel.id]['ctrs_dict'] = {}
            await self._eggtoraid(newraid, channel, author=message.author)
            if egg_level == "0":
                egg_level = utils.get_level(self.bot, newraid)
                self.bot.guild_dict[guild.id][report_dict][channel.id]['exp'] -= 60 * self.bot.raid_info['raid_eggs'][egg_level]['raidtime']

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    @checks.rsvpchannel()
    async def clearstatus(self, ctx, status: str="all"):
        """Clears channel status lists.

        Usage: !clearstatus [status]
        Resets all by default. Supplied [status] can be interested, coming, here, lobby
        Only usable by admins."""
        msg = _("Are you sure you want to clear {status} status for this channel? Everybody will have to RSVP again. If you are wanting to clear one user's status, use `!setstatus <user> cancel`").format(status=status)
        question = await ctx.channel.send(msg)
        report_dict = await utils.get_report_dict(ctx.bot, ctx.channel)
        try:
            timeout = False
            res, reactuser = await utils.ask(self.bot, question, ctx.message.author.id)
        except TypeError:
            timeout = True
        await utils.safe_delete(question)
        if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', u'\U0000274e'):
            return
        elif res.emoji == self.bot.custom_emoji.get('answer_yes', u'\U00002705'):
            pass
        else:
            return
        try:
            if status == "all":
                self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['trainer_dict'] = {}
            else:
                trainer_dict = copy.deepcopy(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['trainer_dict'])
                for trainer in trainer_dict:
                    trainer_dict[trainer]['status'][status] = 0
                self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['trainer_dict'] = trainer_dict
            await ctx.channel.send(_('Meowth! Status lists have been cleared!'), delete_after=10)
        except KeyError:
            pass

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    @checks.rsvpchannel()
    async def setstatus(self, ctx, member: discord.Member, status, *, status_counts: str = ''):
        """Changes raid channel status lists.

        Usage: !setstatus <user> <status> [count]
        User can be a mention or ID number. Status can be maybeinterested/i, coming/c, here/h, lobby, or cancel/x
        Only usable by admins."""
        valid_status_list = ['interested', 'i', 'maybe', 'coming', 'c', 'here', 'h', 'cancel', 'x', 'lobby']
        report_dict = await utils.get_report_dict(self.bot, ctx.channel)
        lobby = self.bot.guild_dict[ctx.channel.guild.id][report_dict][ctx.channel.id].get('lobby', False)
        if status.lower() == "lobby" and not lobby:
            await ctx.message.channel.send(_("Meowth! There is not a lobby to join!"), delete_after=10)
            return
        if status not in valid_status_list:
            await ctx.message.channel.send(_("Meowth! {status} is not a valid status!").format(status=status), delete_after=10)
            return
        ctx.message.content = "{}{} {}".format(ctx.prefix, status, status_counts)
        ctx.message.author = member
        await ctx.bot.process_commands(ctx.message)

    @commands.command()
    @checks.allowarchive()
    async def archive(self, ctx):
        """Marks a raid channel for archival.

        Usage: !archive"""
        message = ctx.message
        channel = message.channel
        await utils.safe_delete(ctx.message)
        report_dict = await utils.get_report_dict(self.bot, ctx.channel)
        self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['archive'] = True
        await asyncio.sleep(10)
        self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['archive'] = True

    """
    Reporting
    """

    @commands.group(aliases=['r', 're', 'egg', 'regg', 'raidegg'], invoke_without_command=True, case_insensitive=True)
    @checks.allowraidreport()
    async def raid(self, ctx, pokemon_or_level=None, *, location:commands.clean_content(fix_channel_mentions=True)="", weather=None, timer=None):
        """Report an ongoing raid or a raid egg.

        Usage: !raid <species/level> <location> [weather] [minutes]
        Meowth will insert <location> into a
        Google maps link and post the link to the same channel the report was made in.
        Meowth's message will also include the type weaknesses of the boss.
        Guided report available with just !raid

        Finally, Meowth will create a separate channel for the raid report, for the purposes of organizing the raid."""
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        error = False
        raid_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/tx_raid_coin.png?cache=1')
        raid_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        while True:
            async with ctx.typing():
                if checks.check_eggchannel(ctx) or checks.check_exeggchannel(ctx):
                    return await ctx.invoke(self.bot.get_command("raid hatch"), pokemon=f"{pokemon_or_level} {location}")
                elif pokemon_or_level and location:
                    content = f"{pokemon_or_level} {location}"
                    if pokemon_or_level.isdigit():
                        new_channel = await self._raidegg(ctx, content)
                    else:
                        new_channel = await self._raid(ctx, content)
                    ctx.raid_channel = new_channel
                    return
                else:
                    def check(reply):
                        if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                            return True
                        else:
                            return False
                    if pokemon_or_level and any([pokemon_or_level == "ex", pokemon_or_level == "meetup", pokemon_or_level == "train", pokemon_or_level.lower() in self.bot.pkmn_list, pokemon_or_level.isdigit()]):
                        pass
                    else:
                        raid_embed.add_field(name=_('**New Raid Report**'), value=_("Meowth! I'll help you report a raid!\n\nFirst, I'll need to know what **pokemon or level** the raid is. Reply with the name of a **pokemon**, an **egg level** number 1-5, or EX. You can reply with **cancel** to stop anytime.\n\nIf you meant to report a **meetup** or **train** reply with **meetup** or **train**."), inline=False)
                        mon_or_lvl_wait = await channel.send(embed=raid_embed)
                        try:
                            mon_or_lvl_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            mon_or_lvl_msg = None
                        await utils.safe_delete(mon_or_lvl_wait)
                        if not mon_or_lvl_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(mon_or_lvl_msg)
                            pokemon_or_level = mon_or_lvl_msg.clean_content.lower()
                    if pokemon_or_level == "cancel":
                        error = _("cancelled the report")
                        break
                    elif pokemon_or_level == "ex":
                        return await ctx.invoke(self.bot.get_command("exraid"))
                    elif pokemon_or_level == "meetup":
                        return await ctx.invoke(self.bot.get_command("meetup"))
                    elif pokemon_or_level == "train":
                        return await ctx.invoke(self.bot.get_command("train"))
                    elif pokemon_or_level.isdigit() and (int(pokemon_or_level) == 0 or int(pokemon_or_level) > 5):
                        error = _("entered an invalid level")
                        break
                    else:
                        pokemon = None
                        if pokemon_or_level.isdigit():
                            raid_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/eggs/{pokemon_or_level}.png?cache=1")
                        else:
                            pokemon, __ = await pkmn_class.Pokemon.ask_pokemon(ctx, pokemon_or_level)
                            if not pokemon or not pokemon.is_raid:
                                error = _("entered a pokemon that doesn't appear in raids")
                                break
                            else:
                                pokemon_or_level = str(pokemon).lower()
                                pokemon.shiny = False
                                pokemon.gender = False
                                pokemon.size = False
                                pokemon.shadow = False
                                raid_embed.set_thumbnail(url=pokemon.img_url)
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**New Raid Report**'), value=f"Great! Now, reply with the **gym** that has the **{'level '+pokemon_or_level if str(pokemon_or_level).isdigit() else str(pokemon_or_level).title()}** raid. You can reply with **cancel** to stop anytime.", inline=False)
                    location_wait = await channel.send(embed=raid_embed)
                    try:
                        location_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        location_msg = None
                    await utils.safe_delete(location_wait)
                    if not location_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(location_msg)
                    if location_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif location_msg:
                        location = location_msg.clean_content
                        gym_matching_cog = self.bot.cogs.get('GymMatching')
                        loc_url = utils.create_gmaps_query(self.bot, location, message.channel, type="raid")
                        gym_info = ""
                        if gym_matching_cog:
                            gym_info, location, gym_url = await gym_matching_cog.get_poi_info(ctx, location, "raid", dupe_check=False, autocorrect=False)
                            if gym_url:
                                loc_url = gym_url
                        if not location:
                            return
                    raid_embed.clear_fields()
                    raid_embed.add_field(name=_('**New Raid Report**'), value=f"Fantastic! Now, reply with the **minutes remaining** before the **{'level '+pokemon_or_level if str(pokemon_or_level).isdigit() else str(pokemon_or_level).title()}** raid {'hatches' if str(pokemon_or_level).isdigit() else 'ends'} at **{location}**. You can reply with **cancel** to stop anytime.", inline=False)
                    expire_wait = await channel.send(embed=raid_embed)
                    try:
                        expire_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        expire_msg = None
                    await utils.safe_delete(expire_wait)
                    if not expire_msg:
                        raidexp = ""
                    else:
                        await utils.safe_delete(expire_msg)
                    if expire_msg and expire_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif expire_msg:
                        raidexp = expire_msg.clean_content
                    raid_embed.remove_field(0)
                    break
        if not error:
            content = f"{pokemon_or_level} {location} {raidexp}"
            if str(pokemon_or_level).isdigit():
                new_channel = await self._raidegg(ctx, content)
            else:
                new_channel = await self._raid(ctx, content)
            ctx.raid_channel = new_channel
        else:
            raid_embed.clear_fields()
            raid_embed.add_field(name=_('**Raid Report Cancelled**'), value=_("Meowth! Your report has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=raid_embed, delete_after=10)
            if not message.embeds:
                await utils.safe_delete(message)

    async def _raid(self, ctx, content):
        message = ctx.message
        help_reaction = self.bot.custom_emoji.get('raid_info', u'\U00002139\U0000fe0f')
        maybe_reaction = self.bot.custom_emoji.get('raid_maybe', u'\U00002753')
        omw_reaction = self.bot.custom_emoji.get('raid_omw', u'\U0001f3ce\U0000fe0f')
        here_reaction = self.bot.custom_emoji.get('raid_here', u'\U0001F4CD')
        cancel_reaction = self.bot.custom_emoji.get('raid_cancel', u'\U0000274C')
        report_emoji = self.bot.custom_emoji.get('raid_report', u'\U0001F4E2')
        list_emoji = self.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f')
        react_list = [maybe_reaction, omw_reaction, here_reaction, cancel_reaction]
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))).strftime(_('%I:%M %p (%H:%M)'))
        raid_split = content.split()
        if len(raid_split) == 0:
            return await ctx.invoke(self.bot.get_command('raid'))
        if raid_split[0] == 'egg':
            return await self._raidegg(ctx, content)
        raidexp = False
        if raid_split[-1].isdigit():
            raidexp = int(raid_split[-1])
            del raid_split[-1]
        elif ':' in raid_split[-1]:
            h, m = re.sub('[a-zA-Z]', '', raid_split[-1]).split(':', maxsplit=1)
            h = '0' if not h else h
            m = '0' if not m else m
            if h.isdigit() and m.isdigit():
                raidexp = (60 * int(h)) + int(m)
            del raid_split[(- 1)]
        weather_list = [_('none'), _('extreme'), _('clear'), _('sunny'), _('rainy'),
                        _('partlycloudy'), _('cloudy'), _('windy'), _('snow'), _('fog')]
        for index, word in enumerate(raid_split):
            weather = re.findall(r"(?=("+'|(?i)'.join(weather_list)+r"))", word)
            if weather:
                weather = str(weather[0]).lower()
                raid_split[index] = ''
                break
            else:
                weather = None
        pokemon, match_list = await pkmn_class.Pokemon.ask_pokemon(ctx, ' '.join(raid_split))
        if not pokemon:
            return await ctx.invoke(self.bot.get_command('raid'))
        elif pokemon.id not in self.bot.raid_list:
            await utils.safe_delete(ctx.message)
            return await ctx.channel.send(f"Meowth! The Pokemon {pokemon.name.title()} does not appear in raids!", delete_after=10)
        matched_boss = False
        level = utils.get_level(self.bot, str(pokemon))
        for boss in self.bot.raid_dict[str(level)]:
            if isinstance(boss, pkmn_class.Pokemon) and str(boss) == str(pokemon):
                pokemon = copy.copy(boss)
                matched_boss = True
                break
        if not matched_boss:
            for boss in self.bot.raid_dict[str(level)]:
                if isinstance(boss, pkmn_class.Pokemon) and boss.id == pokemon.id:
                    if sum(boss.name.title() in s for s in self.bot.raid_info['raid_eggs'][str(level)]['pokemon']) > 1:
                        form_list = [x for x in self.bot.raid_info['raid_eggs'][str(level)]['pokemon'] if boss.name.title() in x]
                        form_list = [x.replace(boss.name.title(), '').strip() for x in form_list]
                        return await ctx.send(f"Meowth! **{boss.name.title()}** has multiple forms at level {str(level)}! Please try again with the form name so I know which one to use! Please choose from: **{(', ').join(form_list)}**", delete_after=10)
                    pokemon = copy.copy(boss)
                    break
        pokemon.shiny = False
        pokemon.gender = False
        pokemon.size = False
        pokemon.shadow = False
        raid_details = " ".join(raid_split).strip()
        for word in match_list:
            raid_details = re.sub(word, '', raid_details, flags=re.IGNORECASE).strip()
        if not raid_details or len(utils.sanitize_channel_name(raid_details)) == 0:
            return await ctx.invoke(self.bot.get_command('raid'))
        raid_gmaps_link = utils.create_gmaps_query(self.bot, raid_details, ctx.channel, type="raid")
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        gym_info = ""
        raid_coordinates = ""
        if gym_matching_cog:
            gym_info, raid_details, gym_url = await gym_matching_cog.get_poi_info(ctx, raid_details, "raid")
            if gym_url:
                raid_gmaps_link = gym_url
                raid_coordinates = gym_url.split('query=')[1]
        if not raid_details:
            return await utils.safe_delete(ctx.message)
        raid_channel = await self.create_raid_channel(ctx, f"{pokemon.name.lower()}{'-'+pokemon.region.lower() if pokemon.region else ''}{'-'+pokemon.form.lower() if pokemon.form else ''}", raid_details, "raid")
        if not raid_channel:
            return
        if not weather and raid_coordinates:
            weather = await self.auto_weather(ctx, raid_coordinates)
        pokemon.weather = weather
        if (raidexp or raidexp is 0) and int(raidexp) > int(self.bot.raid_info['raid_eggs'][level]['raidtime']):
            raidexp = False
            await ctx.send(f"Meowth! That's too long! Level {level} raids currently last no more than {self.bot.raid_info['raid_eggs'][level]['raidtime']} minutes. I'll still try to make the channel and you can correct the time later.", delete_after=10)
        report_details = {
            'address':raid_details,
            'pkmn_obj':str(pokemon),
            'weather':weather,
            'coordinates':raid_coordinates
        }
        raid_embed = await self.make_raid_embed(ctx, report_details, raidexp)
        ctx.raidreport = await message.channel.send(f"Meowth! {str(pokemon).title()} raid reported by {ctx.author.mention}! Details: {raid_details}. Coordinate in {raid_channel.mention}\n\nUse {maybe_reaction} if interested, {omw_reaction} if coming, {here_reaction} if there, {cancel_reaction} to cancel, {report_emoji} to report new, or {list_emoji} to list all raids!", embed=raid_embed)
        await asyncio.sleep(1)
        raidmsg = f"Meowth! {str(pokemon).title()} raid reported by {ctx.author.mention} in {ctx.channel.mention}! Details: {raid_details}. Coordinate here!\n\nClick the {help_reaction} to get help on commands, {maybe_reaction} if interested, {omw_reaction} if coming, {here_reaction} if there, or {cancel_reaction} to cancel!\n\nThis channel will be deleted five minutes after the timer expires."
        raid_message = await raid_channel.send(raidmsg, embed=raid_embed)
        await raid_message.pin()
        self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][raid_channel.id] = {
            'report_channel':ctx.channel.id,
            'report_guild':ctx.guild.id,
            'report_author':ctx.author.id,
            'trainer_dict': {},
            'report_time':time.time(),
            'exp': time.time() + (60 * self.bot.raid_info['raid_eggs'][str(level)]['raidtime']),
            'manual_timer': False,
            'active': True,
            'raid_message':raid_message.id,
            'raid_report':ctx.raidreport.id,
            'raid_embed':raid_embed,
            'report_message':ctx.message.id,
            'address': raid_details,
            'type': 'raid',
            'pokemon': pokemon.name.lower(),
            'pkmn_obj': str(pokemon),
            'egg_level': '0',
            'moveset': 0,
            'weather': weather,
            'coordinates':raid_coordinates
        }
        if raidexp or raidexp is 0:
            await self._timerset(raid_channel, raidexp)
        else:
            timerset_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_date.png?cache=1")
            timerset_embed.add_field(name=f"**Channel Timer**", value=f"If you can, set the time left on the raid using **{ctx.prefix}timerset <minutes>** so others can check it with **{ctx.prefix}timer**.\n\nThe current timer is ***unknown***.")
            timerset_msg = await raid_channel.send(f"Meowth! Hey {ctx.author.mention}!", embed=timerset_embed)
            ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id]['timerset_msg'] = timerset_msg.id
        self.bot.loop.create_task(self.expiry_check(raid_channel))
        weather_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/weatherIcon_large_extreme.png?cache=1")
        weather_embed.add_field(name=f"**Channel Weather**", value=f"The weather is currently set to {str(weather).replace('partlycloudy', 'partly cloudy')}. This may be innaccurate. You can set the correct weather using **{ctx.prefix}weather**.\n\n{'**Boosted**: ' + ('').join([utils.type_to_emoji(self.bot, x) for x in utils.get_weather_boost(str(weather))]) if weather else ''}\n\n{str(pokemon)+' is ***boosted*** in '+str(weather)+' weather.' if pokemon.is_boosted else ''}")
        if weather:
            weather_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/weatherIcon_large_{str(weather).lower()}{'Day' if now.hour >= 6 and now.hour < 18 else 'Night'}.png?cache=1")
        weather_msg = await raid_channel.send(embed=weather_embed)
        ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id]['weather_msg'] = weather_msg.id
        ctrs_dict = await self._get_generic_counters(ctx.channel, str(pokemon), weather)
        if str(level) in self.bot.guild_dict[ctx.guild.id]['configure_dict'].setdefault('counters', {}).setdefault('auto_levels', []):
            try:
                embed = ctrs_dict[0]['embed'] if ctrs_dict else None
                ctrsmsg = f"Here are the best counters for **{str(pokemon)}**! React below to change the moveset."
                ctrsmessage = await raid_channel.send(ctrsmsg, embed=embed)
                ctrsmessage_id = ctrsmessage.id
                await ctrsmessage.pin()
                for moveset in ctrs_dict:
                    await utils.add_reaction(ctrsmessage, ctrs_dict[moveset]['emoji'])
                    await asyncio.sleep(0.25)
            except Exception as e:
                ctrsmessage_id = None
        else:
            ctrsmessage_id = None
        self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][raid_channel.id]['ctrsmessage'] = ctrsmessage_id
        self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][raid_channel.id]['ctrs_dict'] = ctrs_dict
        if not ctx.author.bot:
            raid_reports = self.bot.guild_dict[message.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('reports', {}).setdefault('raid', 0) + 1
            self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['reports']['raid'] = raid_reports
        dm_dict = {}
        index = 0
        for field in raid_embed.fields:
            if "reaction" in field.name.lower() or "status" in field.name.lower() or "team" in field.name.lower():
                raid_embed.remove_field(index)
            else:
                index += 1
        await utils.add_reaction(raid_message, help_reaction)
        for reaction in react_list:
            await asyncio.sleep(0.25)
            await utils.add_reaction(raid_message, reaction)
            await asyncio.sleep(0.25)
            await utils.add_reaction(ctx.raidreport, reaction)
        await utils.add_reaction(ctx.raidreport, report_emoji)
        await utils.add_reaction(ctx.raidreport, list_emoji)
        dm_dict = await self.send_dm_messages(ctx, str(pokemon), raid_details, ctx.raidreport.content.replace(ctx.author.mention, f"{ctx.author.display_name} in {ctx.channel.mention}"), copy.deepcopy(raid_embed), dm_dict)
        self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][raid_channel.id]['dm_dict'] = dm_dict
        return raid_channel

    async def _raidegg(self, ctx, content):
        message = ctx.message
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))).strftime(_('%I:%M %p (%H:%M)'))
        raidexp = False
        hourminute = False
        help_reaction = self.bot.custom_emoji.get('raid_info', u'\U00002139\U0000fe0f')
        maybe_reaction = self.bot.custom_emoji.get('raid_maybe', u'\U00002753')
        omw_reaction = self.bot.custom_emoji.get('raid_omw', u'\U0001f3ce\U0000fe0f')
        here_reaction = self.bot.custom_emoji.get('raid_here', u'\U0001F4CD')
        cancel_reaction = self.bot.custom_emoji.get('raid_cancel', u'\U0000274C')
        report_emoji = self.bot.custom_emoji.get('raid_report', u'\U0001F4E2')
        list_emoji = self.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f')
        react_list = [maybe_reaction, omw_reaction, here_reaction, cancel_reaction]
        raidegg_split = content.split()
        if raidegg_split[0].lower() == 'egg':
            del raidegg_split[0]
        if len(raidegg_split) <= 1:
            return await ctx.invoke(self.bot.get_command('raid'))
        if raidegg_split[0].isdigit():
            egg_level = int(raidegg_split[0])
            del raidegg_split[0]
        else:
            return await ctx.invoke(self.bot.get_command('raid'))
        if (egg_level > 5) or (egg_level < 1):
            return await ctx.channel.send(_('Meowth! Raid egg levels are only from 1-5!'), delete_after=10)
        if raidegg_split[(- 1)].isdigit():
            raidexp = int(raidegg_split[(- 1)])
            del raidegg_split[(- 1)]
        elif ':' in raidegg_split[(- 1)]:
            msg = _("Did you mean egg hatch time {0} or time remaining before hatch {1}?").format("🥚", "⏲")
            question = await ctx.channel.send(msg)
            try:
                timeout = False
                res, reactuser = await utils.ask(self.bot, question, ctx.author.id, react_list=['🥚', '⏲'])
            except TypeError:
                timeout = True
            await utils.safe_delete(question)
            if timeout or res.emoji == '⏲':
                hourminute = True
            elif res.emoji == '🥚':
                now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                start = dateparser.parse(raidegg_split[(- 1)])
                if start.day != now.day:
                    if "m" not in raidegg_split[(- 1)]:
                        start = start + datetime.timedelta(hours=12)
                    start = start.replace(day=now.day)
                timediff = relativedelta(start, now)
                raidexp = (timediff.hours*60) + timediff.minutes + 1
                if raidexp < 0:
                    await ctx.send(_('Meowth! Please enter a time in the future.'), delete_after=10)
                    return
                del raidegg_split[(- 1)]
        if hourminute:
            (h, m) = re.sub('[a-zA-Z]', '', raidegg_split[(- 1)]).split(':', maxsplit=1)
            if h == '':
                h = '0'
            if m == '':
                m = '0'
            if h.isdigit() and m.isdigit():
                raidexp = (60 * int(h)) + int(m)
            del raidegg_split[(- 1)]
        weather_list = [_('none'), _('extreme'), _('clear'), _('sunny'), _('rainy'),
                        _('partlycloudy'), _('cloudy'), _('windy'), _('snow'), _('fog')]
        for index, word in enumerate(raidegg_split):
            weather = re.findall(r"(?=("+'|(?i)'.join(weather_list)+r"))", word)
            if weather:
                weather = str(weather[0]).lower()
                raidegg_split[index] = ''
                break
            else:
                weather = None
        raid_details = ' '.join(raidegg_split).strip()
        if not raid_details or len(utils.sanitize_channel_name(raid_details)) == 0:
            return await ctx.invoke(self.bot.get_command('raid'))
        raid_gmaps_link = utils.create_gmaps_query(self.bot, raid_details, ctx.channel, type="raid")
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        gym_info = ""
        raid_coordinates = ""
        if gym_matching_cog:
            gym_info, raid_details, gym_url = await gym_matching_cog.get_poi_info(ctx, raid_details, "raid")
            if gym_url:
                raid_gmaps_link = gym_url
                raid_coordinates = raid_gmaps_link.split('query=')[1]
        if not raid_details:
            return
        if not weather and raid_coordinates:
            weather = await self.auto_weather(ctx, raid_coordinates)
        egg_level = str(egg_level)
        raid_channel = await self.create_raid_channel(ctx, egg_level, raid_details, "egg")
        if not raid_channel:
            return
        if (raidexp or raidexp is 0) and int(raidexp) > int(self.bot.raid_info['raid_eggs'][str(egg_level)]['hatchtime']):
            raidexp = False
            await ctx.send(f"Meowth! That's too long. Level {egg_level} Raid Eggs currently last no more than {self.bot.raid_info['raid_eggs'][str(egg_level)]['hatchtime']} minutes. I'll still try to make the channel and you can correct the time later.", delete_after=10)
        report_details = {
            'address':raid_details,
            'raid_coordinates':raid_coordinates,
            'egg_level':egg_level
        }
        raid_embed = await self.make_raid_embed(ctx, report_details, raidexp)
        ctx.raidreport = await ctx.channel.send(f"Meowth! Level {egg_level} raid egg reported by {ctx.author.mention}! Details: {raid_details}. Coordinate in {raid_channel.mention}\n\nUse {maybe_reaction} if interested, {omw_reaction} if coming, {here_reaction} if there, {cancel_reaction} to cancel, {report_emoji} to report new, or {list_emoji} to list all raids!", embed=raid_embed)
        await asyncio.sleep(1)
        raidmsg = f"Meowth! Level {egg_level} raid egg reported by {ctx.author.mention} in {ctx.channel.mention}! Details: {raid_details}. Coordinate here!\n\nClick the {help_reaction} to get help on commands, {maybe_reaction} if interested, {omw_reaction} if coming, {here_reaction} if there, or {cancel_reaction} to cancel!\n\nThis channel will be deleted five minutes after the timer expires."
        raid_message = await raid_channel.send(content=raidmsg, embed=raid_embed)
        await raid_message.pin()
        self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][raid_channel.id] = {
            'report_channel':ctx.channel.id,
            'report_guild':ctx.guild.id,
            'report_author':ctx.author.id,
            'trainer_dict': {},
            'report_time':time.time(),
            'exp': time.time() + (60 * self.bot.raid_info['raid_eggs'][egg_level]['hatchtime']),
            'manual_timer': False,
            'active': True,
            'raid_message':raid_message.id,
            'raid_report':ctx.raidreport.id,
            'raid_embed':raid_embed,
            'report_message':ctx.message.id,
            'address': raid_details,
            'type': 'egg',
            'pokemon': '',
            'egg_level':egg_level,
            'weather': weather,
            'moveset': 0,
            'coordinates':raid_coordinates
        }
        if raidexp or raidexp is 0:
            await self._timerset(raid_channel, raidexp)
        else:
            timerset_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_date.png?cache=1")
            timerset_embed.add_field(name=f"**Channel Timer**", value=f"If you can, set the time left on the raid using **{ctx.prefix}timerset <minutes>** so others can check it with **{ctx.prefix}timer**.\n\nThe current timer is ***unknown***.")
            timerset_msg = await raid_channel.send(f"Meowth! Hey {ctx.author.mention}!", embed=timerset_embed)
            ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id]['timerset_msg'] = timerset_msg.id
        self.bot.loop.create_task(self.expiry_check(raid_channel))
        weather_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/weatherIcon_large_extreme.png?cache=1")
        weather_embed.add_field(name=f"**Channel Weather**", value=f"The weather is currently set to {str(weather).replace('partlycloudy', 'partly cloudy')}. This may be innaccurate. You can set the correct weather using **{ctx.prefix}weather**.\n\n{'**Boosted**: ' + ('').join([utils.type_to_emoji(self.bot, x) for x in utils.get_weather_boost(str(weather))]) if weather else ''}")
        if weather:
            weather_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/weatherIcon_large_{str(weather).lower()}{'Day' if now.hour >= 6 and now.hour < 18 else 'Night'}.png?cache=1")
        weather_msg = await raid_channel.send(embed=weather_embed)
        ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id]['weather_msg'] = weather_msg.id
        if not ctx.author.bot:
            egg_reports = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('reports', {}).setdefault('egg', 0) + 1
            self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['reports']['egg'] = egg_reports
        await utils.add_reaction(raid_message, help_reaction)
        for reaction in react_list:
            await asyncio.sleep(0.25)
            await utils.add_reaction(raid_message, reaction)
            await asyncio.sleep(0.25)
            await utils.add_reaction(ctx.raidreport, reaction)
        await utils.add_reaction(ctx.raidreport, report_emoji)
        await utils.add_reaction(ctx.raidreport, list_emoji)
        dm_dict = {}
        dm_dict = await self.send_dm_messages(ctx, str(egg_level), raid_details, ctx.raidreport.content.replace(ctx.author.mention, f"{ctx.author.display_name} in {ctx.channel.mention}"), copy.deepcopy(raid_embed), dm_dict)
        self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][raid_channel.id]['dm_dict'] = dm_dict
        if len(self.bot.raid_info['raid_eggs'][egg_level]['pokemon']) == 1:
            await self._eggassume(ctx, str(self.bot.raid_info['raid_eggs'][egg_level]['pokemon'][0]), raid_channel)
        elif egg_level == "5" and self.bot.guild_dict[raid_channel.guild.id]['configure_dict'].get('settings', {}).get('regional', None) in self.bot.raid_list:
            await self._eggassume(ctx, str(self.bot.guild_dict[raid_channel.guild.id]['configure_dict'].get('settings', {})['regional']), raid_channel)
        return raid_channel

    @raid.command(name='hatch')
    @checks.raidchannel()
    async def raid_hatch(self, ctx, *, pokemon, action="hatch"):
        """Hatch a raid channel if boss is known

        Usage: !raid hatch <pokemon>"""
        report_dict = await utils.get_report_dict(ctx.bot, ctx.channel)
        channel_dict = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]
        egg_level = channel_dict['egg_level']
        if checks.check_hatchedraid(ctx):
            await utils.safe_delete(ctx.message)
            return await ctx.send(f"Meowth! **{ctx.prefix}{ctx.command.parent or ctx.command.name} {action}** is not allowed after it has hatched.", delete_after=10)
        if action == "assume" and self.bot.config.allow_assume.get(egg_level, False) == 'False':
            await utils.safe_delete(ctx.message)
            return await ctx.send(f"Meowth! **{ctx.prefix}{ctx.command.parent or ctx.command.name} {action}** is not allowed in this level egg.", delete_after=10)
        pokemon, __ = await pkmn_class.Pokemon.ask_pokemon(ctx, pokemon)
        if not pokemon:
            await utils.safe_delete(ctx.message)
            return await ctx.send(f"Meowth! I'm missing some details! Usage: {ctx.prefix}{ctx.command.parent or ctx.command.name} **<pokemon>**", delete_after=10)
        pokemon_level = utils.get_level(self.bot, str(pokemon))
        if not pokemon.id in self.bot.raid_list:
            await utils.safe_delete(ctx.message)
            return await ctx.send(f"Meowth! The Pokemon **{pokemon.name.title()}** does not appear in raids!", delete_after=10)
        elif pokemon_level != egg_level:
            await utils.safe_delete(ctx.message)
            return await ctx.send(f"Meowth! The Pokemon **{pokemon.name.title()}** appears in level {pokemon_level} raid eggs, not in level {egg_level} raid eggs!", delete_after=10)
        if sum(pokemon.name.title() in s for s in self.bot.raid_info['raid_eggs'][str(egg_level)]['pokemon']) > 1 and not (pokemon.form or pokemon.region):
            form_list = [x for x in self.bot.raid_info['raid_eggs'][str(egg_level)]['pokemon'] if pokemon.name.title() in x]
            form_list = [x.replace(pokemon.name.title(), '').strip() for x in form_list]
            await utils.safe_delete(ctx.message)
            return await ctx.send(f"Meowth! **{pokemon.name.title()}** has multiple forms at level {str(egg_level)}! Please try again with the form name so I know which one to use! Please choose from: **{(', ').join(form_list)}**", delete_after=10)
        if self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['active'] == False:
            return await self._eggtoraid(str(pokemon), ctx.channel, ctx.author)
        else:
            if action == "assume":
                return await self._eggassume(ctx, str(pokemon), ctx.channel, ctx.author)
            else:
                await utils.safe_delete(ctx.message)
                return await ctx.channel.send(f"Meowth! Please wait until the egg has hatched before changing it to an open raid!", delete_after=10)

    @raid.command(name='assume')
    @checks.raidchannel()
    async def raid_assume(self, ctx, *, pokemon):
        """Assume a raid channel if boss is known

        Usage: !raid assume <pokemon>"""
        await ctx.invoke(self.bot.get_command("raid hatch"), pokemon=pokemon, action="assume")

    async def _eggassume(self, ctx, args, raid_channel, author=None):
        report_dict = await utils.get_report_dict(ctx.bot, raid_channel)
        if 'raidchannel' not in str(report_dict):
            return
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
        eggdetails = self.bot.guild_dict[ctx.guild.id][report_dict][raid_channel.id]
        report_channel = self.bot.get_channel(eggdetails['report_channel'])
        egg_level = eggdetails['egg_level']
        manual_timer = eggdetails['manual_timer']
        weather = eggdetails.get('weather', None)
        dm_dict = eggdetails.get('dm_dict', {})
        egg_report = await report_channel.fetch_message(eggdetails['raid_report'])
        raid_message = await raid_channel.fetch_message(eggdetails['raid_message'])
        coordinates = eggdetails.get('coordinates', False)
        if coordinates:
            weather = await self.auto_weather(ctx, coordinates)
        boss_list = []
        pokemon, match_list = await pkmn_class.Pokemon.ask_pokemon(ctx, args)
        matched_boss = False
        for boss in self.bot.raid_dict[str(egg_level)]:
            if isinstance(boss, pkmn_class.Pokemon):
                boss_list.append(boss.name.lower())
                if str(boss) == str(pokemon):
                    pokemon = copy.copy(boss)
                    matched_boss = True
                    break
        if not matched_boss:
            for boss in self.bot.raid_dict[str(egg_level)]:
                if isinstance(boss, pkmn_class.Pokemon) and boss.id == pokemon.id:
                    if sum(boss.name.title() in s for s in self.bot.raid_info['raid_eggs'][str(egg_level)]['pokemon']) > 1:
                        return
                    pokemon = copy.copy(boss)
                    break
        if pokemon.name.lower() not in boss_list:
            return
        pokemon.weather = weather
        if weather != eggdetails.get('weather') or pokemon.is_boosted:
            weather_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/weatherIcon_large_extreme.png?cache=1")
            weather_embed.add_field(name=f"**Channel Weather**", value=f"The weather is currently set to {str(weather).replace('partlycloudy', 'partly cloudy')}. This may be innaccurate. You can set the correct weather using **{ctx.prefix}weather**.\n\n{'**Boosted**: ' + ('').join([utils.type_to_emoji(self.bot, x) for x in utils.get_weather_boost(str(weather))]) if weather else ''}\n\n{str(pokemon)+' is ***boosted*** in '+str(weather)+' weather.' if pokemon.is_boosted else ''}")
            if weather:
                weather_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/weatherIcon_large_{str(weather).lower()}{'Day' if now.hour >= 6 and now.hour < 18 else 'Night'}.png?cache=1")
            try:
                weather_msg = await raid_channel.fetch_message(self.bot.guild_dict[ctx.guild.id][report_dict][raid_channel.id]['weather_msg'])
                await weather_msg.edit(embed=weather_embed)
            except Exception as e:
                pass
        self.bot.guild_dict[ctx.guild.id][report_dict][raid_channel.id]['pokemon'] = pokemon.name.lower()
        self.bot.guild_dict[ctx.guild.id][report_dict][raid_channel.id]['pkmn_obj'] = str(pokemon)
        if raid_channel.id in self.bot.active_channels.keys():
            self.bot.active_channels[raid_channel.id]['pokemon'] = pokemon
        oldembed = raid_message.embeds[0]
        raid_gmaps_link = oldembed.url
        shiny_str = ""
        if "raid" in pokemon.shiny_available:
            shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
        raid_embed = discord.Embed(title=_('Meowth! Click here for directions to the coming level {level} raid!').format(level=egg_level), description=oldembed.description, url=raid_gmaps_link, colour=ctx.guild.me.colour)
        raid_embed.add_field(name=_('**Details:**'), value=f"{shiny_str}{str(pokemon)} {pokemon.emoji}\n{pokemon.is_boosted if pokemon.is_boosted else ''}", inline=True)
        raid_embed.add_field(name=_('**Weaknesses:**'), value=_('{weakness_list}\u200b').format(weakness_list=pokemon.weakness_emoji), inline=True)
        index = 0
        for field in oldembed.fields:
            if _('group') in field.name.lower() or _('expires') in field.name.lower() or _('hatches') in field.name.lower() or _('list') in field.name.lower() or _('event') in field.name.lower():
                raid_embed.add_field(name=field.name, value=field.value, inline=field.inline)
            else:
                index += 1
        raid_embed.set_footer(text=oldembed.footer.text, icon_url=oldembed.footer.icon_url)
        raid_embed.set_thumbnail(url=oldembed.thumbnail.url)
        raid_embed.set_author(name=oldembed.author.name, icon_url=oldembed.author.icon_url)
        ctx.raidreport = egg_report
        ctx.raid_channel = raid_channel
        if ctx.raidreport:
            self.bot.loop.create_task(self.edit_dm_messages(ctx, egg_report.content, copy.deepcopy(raid_embed), dm_dict))
        try:
            await raid_message.edit(new_content=raid_message.content, embed=raid_embed, content=raid_message.content)
        except discord.errors.NotFound:
            raid_message = None
        try:
            await egg_report.edit(new_content=egg_report.content, embed=raid_embed, content=egg_report.content)
        except discord.errors.NotFound:
            egg_report = None
        assume_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url=pokemon.img_url)
        assume_embed.add_field(name=f"Raid Assumed", value=f"Meowth! This egg will be assumed to be {str(pokemon)} when it hatches!")
        await raid_channel.send(embed=assume_embed, delete_after=600)
        ctrs_dict = await self._get_generic_counters(ctx.channel, str(pokemon), weather)
        if str(egg_level) in self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('counters', {}).get('auto_levels', []):
            embed = ctrs_dict[0]['embed'] if ctrs_dict else None
            ctrsmsg = f"Here are the best counters for **{str(pokemon)}**! React below to change the moveset."
            ctrsmessage = await raid_channel.send(content=ctrsmsg, embed=embed)
            ctrsmessage_id = ctrsmessage.id
            await ctrsmessage.pin()
            for moveset in ctrs_dict:
                await utils.add_reaction(ctrsmessage, ctrs_dict[moveset]['emoji'])
                await asyncio.sleep(0.25)
        else:
            ctrsmessage_id = eggdetails.get('ctrsmessage', None)
        eggdetails['ctrs_dict'] = ctrs_dict
        eggdetails['ctrsmessage'] = ctrsmessage_id
        self.bot.guild_dict[ctx.guild.id][report_dict][raid_channel.id] = eggdetails

    async def _eggtoraid(self, entered_raid, raid_channel, author=None, moveset=None):
        report_dict = await utils.get_report_dict(self.bot, raid_channel)
        if 'raidchannel' not in str(report_dict):
            return
        help_reaction = self.bot.custom_emoji.get('raid_info', u'\U00002139\U0000fe0f')
        maybe_reaction = self.bot.custom_emoji.get('raid_maybe', u'\U00002753')
        omw_reaction = self.bot.custom_emoji.get('raid_omw', u'\U0001f3ce\U0000fe0f')
        here_reaction = self.bot.custom_emoji.get('raid_here', u'\U0001F4CD')
        cancel_reaction = self.bot.custom_emoji.get('raid_cancel', u'\U0000274C')
        report_emoji = self.bot.custom_emoji.get('raid_report', u'\U0001F4E2')
        list_emoji = self.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f')
        eggdetails = self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id]
        report_channel = self.bot.get_channel(eggdetails['report_channel'])
        raid_message = await raid_channel.fetch_message(eggdetails['raid_message'])
        ctx = await self.bot.get_context(raid_message)
        if not ctx.prefix:
            prefix = self.bot._get_prefix(self.bot, ctx.message)
            ctx.prefix = prefix[-1]
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
        egg_level = eggdetails['egg_level']
        if egg_level == "0":
            egg_level = utils.get_level(self.bot, entered_raid)
        boss_list = []
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, entered_raid)
        matched_boss = False
        for boss in self.bot.raid_dict[str(egg_level)]:
            if isinstance(boss, pkmn_class.Pokemon):
                boss_list.append(boss.name.lower())
                if str(boss) == str(pokemon):
                    pokemon = copy.copy(boss)
                    matched_boss = True
                    break
        if not matched_boss:
            for boss in self.bot.raid_dict[str(egg_level)]:
                if isinstance(boss, pkmn_class.Pokemon) and pokemon and boss.id == pokemon.id:
                    if sum(boss.name.title() in s for s in self.bot.raid_info['raid_eggs'][str(egg_level)]['pokemon']) > 1:
                        form_list = [x for x in self.bot.raid_info['raid_eggs'][str(egg_level)]['pokemon'] if boss.name.title() in x]
                        form_list = [x.replace(boss.name.title(), '').strip() for x in form_list]
                        return await raid_channel.send(f"Meowth! **{boss.name.title()}** has multiple forms at level {str(egg_level)}! Please try again with the form name so I know which one to use! Please choose from: **{(', ').join(form_list)}**", delete_after=10)
                    pokemon = copy.copy(boss)
                    break
        weather = eggdetails.get('weather')
        raid_coordinates = eggdetails.get('coordinates')
        if raid_coordinates:
            weather = await self.auto_weather(ctx, raid_coordinates)
        pokemon.weather = weather
        if weather != eggdetails.get('weather') or pokemon.is_boosted:
            weather_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/weatherIcon_large_extreme.png?cache=1")
            weather_embed.add_field(name=f"**Channel Weather**", value=f"The weather is currently set to {str(weather).replace('partlycloudy', 'partly cloudy')}. This may be innaccurate. You can set the correct weather using **{ctx.prefix}weather**.\n\n{'**Boosted**: ' + ('').join([utils.type_to_emoji(self.bot, x) for x in utils.get_weather_boost(str(weather))]) if weather else ''}\n\n{str(pokemon)+' is ***boosted*** in '+str(weather)+' weather.' if pokemon.is_boosted else ''}")
            if weather:
                weather_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/weatherIcon_large_{str(weather).lower()}{'Day' if now.hour >= 6 and now.hour < 18 else 'Night'}.png?cache=1")
            try:
                weather_msg = await ctx.channel.fetch_message(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['weather_msg'])
                await weather_msg.edit(embed=weather_embed)
            except:
                pass
        pokemon.shiny = False
        pokemon.gender = False
        pokemon.size = False
        try:
            egg_report = await report_channel.fetch_message(eggdetails['raid_report'])
        except (discord.errors.NotFound, discord.errors.HTTPException):
            egg_report = None
        next_trains = eggdetails.get('next_trains', None)
        if not author:
            author = ctx.guild.get_member(eggdetails['report_author'])
        ctx.author = author
        if pokemon.name.lower() not in boss_list:
            await raid_channel.send(_('Meowth! The Pokemon {pokemon} does not hatch from level {level} raid eggs!').format(pokemon=str(pokemon).title(), level=egg_level), delete_after=10)
            return
        if (egg_level.isdigit() and int(egg_level) > 0) or egg_level == 'EX':
            raid_expire = eggdetails['exp'] + 60 * self.bot.raid_info['raid_eggs'][str(egg_level)]['raidtime']
        else:
            raid_expire = eggdetails['exp']
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[raid_channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
        end = datetime.datetime.utcfromtimestamp(raid_expire) + datetime.timedelta(hours=self.bot.guild_dict[raid_channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
        raidexp = (end-now).total_seconds()/60
        report_details = {
            'address': eggdetails['address'],
            'coordinates': eggdetails.get('coordinates'),
            'pkmn_obj':str(pokemon),
            'moves':eggdetails.get('moves'),
            'weather':weather
        }
        oldembed = raid_message.embeds[0]
        raid_embed = await self.make_raid_embed(ctx, report_details, raidexp)
        for field in oldembed.fields:
            if _('list') in field.name.lower():
                raid_embed.add_field(name=field.name, value=field.value, inline=field.inline)
        if egg_level.isdigit():
            hatchtype = 'raid'
            raidreportcontent = f"Meowth! The egg has hatched into a {str(pokemon)} raid! Details: {eggdetails['address']}. Coordinate in {raid_channel.mention}\n\nUse {maybe_reaction} if interested, {omw_reaction} if coming, {here_reaction} if there, {cancel_reaction} to cancel, {report_emoji} to report new, or {list_emoji} to list all raids!"
            raidmsg = f"Meowth! The egg reported by {author.mention} in {report_channel.mention} hatched into a {str(pokemon)} raid! Details: {eggdetails['address']}. Coordinate here!\n\nClick the {help_reaction} to get help on commands, {maybe_reaction} if interested, {omw_reaction} if coming, {here_reaction} if there, or {cancel_reaction} to cancel!\n\nThis channel will be deleted five minutes after the timer expires."
        elif egg_level == 'EX':
            hatchtype = 'exraid'
            if self.bot.guild_dict[raid_channel.guild.id]['configure_dict'].get('invite', {}).get('enabled', False):
                invitemsgstr = _("Use the **!invite** in {report_channel} command to gain access and coordinate").format(report_channel=report_channel.mention)
                invitemsgstr2 = _(" after using **!invite** in {report_channel} to gain access").format(report_channel=report_channel.mention)
            else:
                invitemsgstr = _("Coordinate")
                invitemsgstr2 = ""
            raidreportcontent = _('Meowth! The EX egg has hatched into a {pokemon} raid! Details: {location_details}. {invitemsgstr} coordinate in {raid_channel}').format(pokemon=str(pokemon), location_details=eggdetails['address'], invitemsgstr=invitemsgstr, raid_channel=raid_channel.mention)
            raidmsg = f"Meowth! {str(pokemon)} EX raid reported by {author.mention} in {report_channel.mention}! Details: {eggdetails['address']}. Coordinate here{invitemsgstr2}!\n\nClick the {help_reaction} to get help on commands, {maybe_reaction} if interested, {omw_reaction} if coming, {here_reaction} if there, or {cancel_reaction} to cancel!\n\nThis channel will be deleted five minutes after the timer expires."
        trainer_list = []
        trainer_dict = copy.deepcopy(self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id]['trainer_dict'])
        for trainer in trainer_dict.keys():
            user = raid_channel.guild.get_member(trainer)
            if not user:
                continue
            if (trainer_dict[trainer].get('interest', None)) and (str(pokemon).lower() not in trainer_dict[trainer]['interest']):
                self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id]['trainer_dict'][trainer]['status'] = {'maybe':0, 'coming':0, 'here':0, 'lobby':0}
                self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id]['trainer_dict'][trainer]['party'] = {'mystic':0, 'valor':0, 'instinct':0, 'unknown':0}
                self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id]['trainer_dict'][trainer]['count'] = 1
            else:
                self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id]['trainer_dict'][trainer]['interest'] = []
        await asyncio.sleep(1)
        trainer_dict = copy.deepcopy(self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id]['trainer_dict'])
        for trainer in trainer_dict.keys():
            if (trainer_dict[trainer]['status']['maybe']) or (trainer_dict[trainer]['status']['coming']) or (trainer_dict[trainer]['status']['here']):
                user = raid_channel.guild.get_member(trainer)
                if not user:
                    continue
                trainer_list.append(user.mention)
        hatch_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url=pokemon.img_url)
        hatch_embed.add_field(name="**Raid Hatched**", value=f"Meowth! The raid egg has just hatched into a {str(pokemon)} raid!")
        hatch_msg = await raid_channel.send(f"{'Hatched - Trainers ' if trainer_list else ''}{(', ').join(trainer_list) if trainer_list else ''}", embed=hatch_embed, delete_after=600)
        ctx = await self.bot.get_context(hatch_msg)
        ctx.raidreport = egg_report
        ctx.raid_channel = raid_channel
        self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id]['exp'] = raid_expire
        self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id]['type'] = hatchtype
        self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id]['trainer_dict'] = trainer_dict
        self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id]['active'] = True
        self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id]['pokemon'] = pokemon.name.lower()
        self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id]['pkmn_obj'] = str(pokemon)
        if raid_channel.id in self.bot.active_channels.keys():
            self.bot.active_channels[raid_channel.id]['pokemon'] = pokemon
        self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id]['egg_level'] = '0'
        self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id]['moveset'] = 0
        setting_category = self.bot.get_channel(self.bot.guild_dict[raid_channel.guild.id]['configure_dict']['raid']['category_dict'][egg_level])
        if setting_category and setting_category != raid_channel.category and len(setting_category.text_channels) < 50:
            await raid_channel.edit(category=setting_category)
        raid_channel_name = await self.edit_channel_name(raid_channel)
        await raid_channel.edit(name=raid_channel_name, topic=end.strftime(_('Ends on %B %d at %I:%M %p (%H:%M)')))
        try:
            await raid_message.edit(new_content=raidmsg, embed=raid_embed, content=raidmsg)
            raid_message = raid_message.id
        except (discord.errors.NotFound, AttributeError):
            raid_message = None
        try:
            await egg_report.edit(new_content=raidreportcontent, embed=raid_embed, content=raidreportcontent)
            egg_report = egg_report.id
        except (discord.errors.NotFound, AttributeError):
            egg_report = None
        self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id]['raid_message'] = raid_message
        self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id]['raid_report'] = egg_report
        try:
            timerstr = await self.print_raid_timer(raid_channel)
            timerset_embed = discord.Embed(colour=raid_channel.guild.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_date.png?cache=1")
            timerset_embed.add_field(name=f"**Channel Timer**", value=f"{timerstr}")
            if self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id].get('timerset_msg'):
                timerset_msg = await raid_channel.fetch_message(self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id]['timerset_msg'])
                await timerset_msg.edit(content=None, embed=timerset_embed)
        except:
            pass
        self.bot.loop.create_task(self.expiry_check(raid_channel))
        try:
            hatch_message = await raid_channel.fetch_message(self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id]['hatch_message'])
            await utils.safe_delete(hatch_message)
            del self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id]['hatch_message']
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, KeyError):
            pass
        ctrsmessage_id = eggdetails.get('ctrsmessage', None)
        ctrsmessage = self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id].get('ctrsmessage', None)
        ctrs_dict = self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id].get('ctrs_dict', {})
        ctrs_dict = await self._get_generic_counters(raid_channel, str(pokemon), weather)
        if str(egg_level) in self.bot.guild_dict[raid_channel.guild.id]['configure_dict'].get('counters', {}).get('auto_levels', []) and str(pokemon) and not ctrsmessage:
            embed = ctrs_dict[0]['embed'] if ctrs_dict else None
            ctrsmsg = f"Here are the best counters for **{str(pokemon)}**! React below to change the moveset."
            ctrsmessage = await raid_channel.send(content=ctrsmsg, embed=embed)
            ctrsmessage_id = ctrsmessage.id
            await ctrsmessage.pin()
            for moveset in ctrs_dict:
                await utils.add_reaction(ctrsmessage, ctrs_dict[moveset]['emoji'])
                await asyncio.sleep(0.25)
        self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id]['ctrs_dict'] = ctrs_dict
        self.bot.guild_dict[raid_channel.guild.id][report_dict][raid_channel.id]['ctrsmessage'] = ctrsmessage_id
        if author and not author.bot:
            raid_reports = self.bot.guild_dict[raid_channel.guild.id].setdefault('trainers', {}).setdefault(author.id, {}).setdefault('reports', {}).setdefault('raid', 0) + 1
            self.bot.guild_dict[raid_channel.guild.id]['trainers'][author.id]['reports']['raid'] = raid_reports
            await self._edit_party(raid_channel, author)
        if ctx.raidreport:
            self.bot.loop.create_task(self.edit_dm_messages(ctx, raidreportcontent, copy.deepcopy(raid_embed), eggdetails.get('dm_dict', {})))

    @raid.command(aliases=['expire', 'delete'], name='reset')
    @checks.allowraidreport()
    @checks.is_mod()
    async def reset_raids(self, ctx, *, channel:discord.TextChannel=None):
        """Expire raids, meetups, trains

        Usage: !raid/exraid/train/meetup reset"""
        await self.raid_reset(ctx, channel, type="raid")

    async def raid_reset(self, ctx, channel, type):
        if type == "exraid":
            report_dict = 'exraidchannel_dict'
        elif type == "meetup":
            report_dict = 'meetup_dict'
        elif type == "train":
            report_dict = 'raidtrain_dict'
        else:
            report_dict = 'raidchannel_dict'
        raid_dict = copy.deepcopy(self.bot.guild_dict[ctx.guild.id].setdefault(report_dict, {}))
        reset_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/unicode_dash.png?cache=1')
        if channel and channel.id not in raid_dict:
            channel = None
        if not channel and ctx.channel.id in raid_dict:
            channel = ctx.channel
        if not channel:
            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel
            reset_embed.add_field(name=f"**Reset {type.title()} Reports**", value=f"**Meowth!** {ctx.author.mention}, Reply with a channel mention of the {type} you'd like to delete or **all** to reset all {type} channels{' or a **number** to reset all of that level' if type == 'raid' else ''}. If you want to stop, reply with **cancel**.")
            raid_wait = await ctx.send(embed=reset_embed)
            try:
                raid_reply = await self.bot.wait_for('message', timeout=60, check=check)
                await utils.safe_delete(raid_wait)
            except asyncio.TimeoutError:
                return await utils.safe_delete(raid_wait)
            if raid_reply.content.lower() == "cancel":
                await utils.safe_delete(raid_wait)
                reset_embed.clear_fields()
                reset_embed.add_field(name=f"Reset Cancelled", value=f"Your {type} reset request has been canceled. No changes have been made.")
                return await ctx.send(embed=reset_embed, delete_after=10)
            elif raid_reply.content.lower() == "all" or (raid_reply.content.isdigit() and int(raid_reply.content) <= 5):
                await utils.safe_delete(raid_reply)
                async with ctx.typing():
                    for raid_id in raid_dict:
                        if self.bot.guild_dict[ctx.guild.id][report_dict][raid_id]['egg_level'] != str(raid_reply.content) and raid_reply.content.isdigit():
                            continue
                        channel = ctx.bot.get_channel(raid_id)
                        if not channel:
                            continue
                        self.bot.guild_dict[ctx.guild.id][report_dict][channel.id]['delete'] = True
                        self.bot.guild_dict[ctx.guild.id][report_dict][channel.id]['exp'] = time.time()
                        self.bot.loop.create_task(self.expire_channel(channel))
            else:
                converter = commands.TextChannelConverter()
                try:
                    channel = await converter.convert(ctx, raid_reply.content.lower())
                except:
                    pass
                if not channel:
                    reset_embed.clear_fields()
                    reset_embed.add_field(name=f"Reset Cancelled", value=f"Your {type} reset request has been canceled. No changes have been made.")
                    return await ctx.send(embed=reset_embed, delete_after=10)
                self.bot.guild_dict[ctx.guild.id][report_dict][channel.id]['delete'] = True
                self.bot.guild_dict[ctx.guild.id][report_dict][channel.id]['exp'] = time.time()
                self.bot.loop.create_task(self.expire_channel(channel))

    @commands.group(aliases=['ex'], invoke_without_command=True, case_insensitive=True)
    @checks.allowexraidreport()
    async def exraid(self, ctx, *, location:commands.clean_content(fix_channel_mentions=True)=None):
        """Report an upcoming EX raid.

        Usage: !exraid <location>
        Meowth will insert the details (really just everything after the species name) into a
        Google maps link and post the link to the same channel the report was made in.
        Meowth's message will also include the type weaknesses of the boss.
        Guided report available with just !exraid

        Finally, Meowth will create a separate channel for the raid report, for the purposes of organizing the raid."""
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        error = False
        raid_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/tx_raid_coin_exclusive.png?cache=1')
        raid_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        while True:
            async with ctx.typing():
                if checks.check_exeggchannel(ctx):
                    return await ctx.invoke(self.bot.get_command("raid hatch"), pokemon=location)
                if location and location.split()[0].lower() == "raid":
                    location = " ".join(location.split()[1:])
                if location:
                    pkmn_match = next((p for p in self.bot.pkmn_list if re.sub('[^a-zA-Z0-9]', '', p) == re.sub('[^a-zA-Z0-9]', '', location.lower())), None)
                    if pkmn_match:
                        location = location.replace(pkmn_match, '').strip()
                if location:
                    new_channel = await self._exraid(ctx, location)
                    ctx.raid_channel = new_channel
                    return
                else:
                    def check(reply):
                        if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                            return True
                        else:
                            return False
                    raid_embed.add_field(name=_('**New EX Raid Report**'), value=_("Meowth! I'll help you report an EX raid!\n\nWhat's the name of the **gym** that has the **EX** raid? You can reply with **cancel** to stop anytime."), inline=False)
                    location_wait = await channel.send(embed=raid_embed)
                    try:
                        location_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        location_msg = None
                    await utils.safe_delete(location_wait)
                    if not location_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(location_msg)
                    if location_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif location_msg:
                        location = location_msg.clean_content
                        gym_matching_cog = self.bot.cogs.get('GymMatching')
                        loc_url = utils.create_gmaps_query(self.bot, location, message.channel, type="raid")
                        gym_info = ""
                        if gym_matching_cog:
                            gym_info, location, gym_url = await gym_matching_cog.get_poi_info(ctx, location, "raid", dupe_check=False, autocorrect=False)
                            if gym_url:
                                loc_url = gym_url
                        if not location:
                            return
        if not error:
            new_channel = await self._exraid(ctx, location)
            ctx.raid_channel = new_channel
            return
        else:
            raid_embed.clear_fields()
            raid_embed.add_field(name=_('**EX Raid Report Cancelled**'), value=_("Meowth! Your report has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=raid_embed, delete_after=10)
            if not message.embeds:
                await utils.safe_delete(message)

    async def _exraid(self, ctx, location):
        message = ctx.message
        channel = message.channel
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))).strftime(_('%I:%M %p (%H:%M)'))
        help_reaction = self.bot.custom_emoji.get('raid_info', u'\U00002139\U0000fe0f')
        maybe_reaction = self.bot.custom_emoji.get('raid_maybe', u'\U00002753')
        omw_reaction = self.bot.custom_emoji.get('raid_omw', u'\U0001f3ce\U0000fe0f')
        here_reaction = self.bot.custom_emoji.get('raid_here', u'\U0001F4CD')
        cancel_reaction = self.bot.custom_emoji.get('raid_cancel', u'\U0000274C')
        report_emoji = self.bot.custom_emoji.get('raid_report', u'\U0001F4E2')
        list_emoji = self.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f')
        react_list = [maybe_reaction, omw_reaction, here_reaction, cancel_reaction]
        report_dict = await utils.get_report_dict(ctx.bot, ctx.channel)
        raid_details = location
        raid_details = raid_details.strip()
        raid_gmaps_link = utils.create_gmaps_query(self.bot, raid_details, message.channel, type="exraid")
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        gym_info = ""
        raid_coordinates = ""
        if gym_matching_cog:
            gym_info, raid_details, gym_url = await gym_matching_cog.get_poi_info(ctx, raid_details, "exraid")
            if gym_url:
                raid_gmaps_link = gym_url
                raid_coordinates = gym_url.split('query=')[1]
        if not raid_details:
            return
        report_details = {
            'address':raid_details,
            'egg_level':"EX"
        }
        raid_embed = await self.make_raid_embed(ctx, report_details)
        raid_channel = await self.create_raid_channel(ctx, "EX", raid_details, "exraid")
        if not raid_channel:
            return
        raid_img_url = "https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/tx_raid_coin_exclusive.png?cache=1"
        if self.bot.guild_dict[channel.guild.id]['configure_dict'].get('invite', {}).get('enabled', False):
            invitemsgstr = _("Use the **!invite** command to gain access and coordinate")
            invitemsgstr2 = _(" after using **!invite** to gain access")
        else:
            invitemsgstr = _("Coordinate")
            invitemsgstr2 = ""
        ctx.raidreport = await channel.send(content=f"Meowth! EX raid egg reported by {message.author.mention}! Details: {raid_details}. {invitemsgstr} in {raid_channel.mention}\n\nUse {maybe_reaction} if interested, {omw_reaction} if coming, {here_reaction} if there, {cancel_reaction} to cancel, {report_emoji} to report new, or {list_emoji} to list all raids!", embed=raid_embed)
        await asyncio.sleep(1)
        raidmsg = f"Meowth! EX raid reported by {message.author.mention} in {message.channel.mention}! Details: {raid_details}. Coordinate here{invitemsgstr2}!\n\nClick the {help_reaction} to get help on commands, {maybe_reaction} if interested, {omw_reaction} if coming, {here_reaction} if there, or {cancel_reaction} to cancel!\n\nThis channel will be deleted five minutes after the timer expires."
        raid_message = await raid_channel.send(content=raidmsg, embed=raid_embed)
        await raid_message.pin()
        self.bot.guild_dict[message.guild.id]['exraidchannel_dict'][raid_channel.id] = {
            'report_channel':channel.id,
            'report_guild':message.guild.id,
            'report_author':message.author.id,
            'trainer_dict': {},
            'report_time':time.time(),
            'exp': time.time() + (((60 * 60) * 24) * self.bot.raid_info['raid_eggs']['EX']['hatchtime']),
            'manual_timer': False,
            'active': True,
            'raid_message':raid_message.id,
            'raid_report':ctx.raidreport.id,
            'raid_embed':raid_embed,
            'report_message':message.id,
            'address': raid_details,
            'type': 'egg',
            'pokemon': '',
            'egg_level':'EX',
            'coordinates':raid_coordinates
        }
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[raid_channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
        ow = raid_channel.overwrites_for(ctx.author)
        ow.send_messages = True
        ow.read_messages = True
        try:
            await raid_channel.set_permissions(ctx.author, overwrite=ow)
        except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.InvalidArgument):
            pass
        timerset_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_date.png?cache=1")
        timerset_embed.add_field(name=f"**Channel Timer**", value=f"If you can, set the time left on the raid using **{ctx.prefix}timerset <date and time>** so others can check it with **{ctx.prefix}timer**. **<date and time>** can be written exactly how it appears on your EX Raid Pass.\n\nThe current timer is ***unknown***.")
        timerset_msg = await raid_channel.send(f"Meowth! Hey {ctx.author.mention}!", embed=timerset_embed)
        ctx.bot.guild_dict[message.guild.id]['exraidchannel_dict'][raid_channel.id]['timerset_msg'] = timerset_msg.id
        self.bot.loop.create_task(self.expiry_check(raid_channel))
        weather = None
        weather_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/weatherIcon_large_extreme.png?cache=1")
        weather_embed.add_field(name=f"**Channel Weather**", value=f"The weather is currently set to None. This may be innaccurate. You can set the correct weather using **{ctx.prefix}weather**.\n\n{'**Boosted**: ' + ('').join([utils.type_to_emoji(self.bot, x) for x in utils.get_weather_boost(str(weather))]) if weather else ''}")
        weather_msg = await raid_channel.send(embed=weather_embed)
        self.bot.guild_dict[ctx.guild.id]['exraidchannel_dict'][raid_channel.id]['weather_msg'] = weather_msg.id
        ex_reports = self.bot.guild_dict[message.guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('reports', {}).setdefault('ex', 0) + 1
        self.bot.guild_dict[message.guild.id]['trainers'][message.author.id]['reports']['ex'] = ex_reports
        await utils.add_reaction(raid_message, help_reaction)
        for reaction in react_list:
            await asyncio.sleep(0.25)
            await utils.add_reaction(raid_message, reaction)
            await asyncio.sleep(0.25)
            await utils.add_reaction(ctx.raidreport, reaction)
        await utils.add_reaction(ctx.raidreport, report_emoji)
        await utils.add_reaction(ctx.raidreport, list_emoji)
        dm_dict = {}
        dm_dict = await self.send_dm_messages(ctx, "EX", raid_details, ctx.raidreport.content.replace(ctx.author.mention, f"{ctx.author.display_name} in {ctx.channel.mention}"), copy.deepcopy(raid_embed), dm_dict)
        self.bot.guild_dict[ctx.guild.id]['exraidchannel_dict'][raid_channel.id]['dm_dict'] = dm_dict
        if len(self.bot.raid_info['raid_eggs']['EX']['pokemon']) == 1:
            await self._eggassume(ctx, str(self.bot.raid_info['raid_eggs']['EX']['pokemon'][0]), raid_channel)
        return raid_channel

    @exraid.command(name='assume', hidden=True)
    @checks.raidchannel()
    async def exraid_assume(self, ctx, *, pokemon: pkmn_class.Pokemon):
        await ctx.invoke(self.bot.get_command("raid hatch"), pokemon=pokemon, action="assume")

    @exraid.command(name='hatch', hidden=True)
    @checks.raidchannel()
    async def exraid_hatch(self, ctx, *, pokemon: pkmn_class.Pokemon):
        await ctx.invoke(self.bot.get_command("raid hatch"), pokemon=pokemon)

    @exraid.command(aliases=['expire', 'delete'], name='reset')
    @checks.allowexraidreport()
    @checks.is_mod()
    async def reset_exraids(self, ctx, *, channel:discord.TextChannel=None):
        await self.raid_reset(ctx, channel, type='exraid')

    @commands.command()
    @checks.allowinvite()
    async def invite(self, ctx, *, exraid_choice: int=None):
        """Join an EX Raid.

        Usage: !invite"""
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        error = False
        exraidlist = ''
        exraid_dict = {}
        exraidcount = 0
        rc_dict = {**self.bot.guild_dict[guild.id]['raidchannel_dict'], **self.bot.guild_dict[guild.id]['exraidchannel_dict']}
        await utils.safe_delete(ctx.message)
        for channelid in rc_dict:
            if (not discord.utils.get(guild.text_channels, id=channelid)):
                continue
            if (rc_dict[channelid]['egg_level'] == 'EX') or (rc_dict[channelid]['type'] == 'exraid'):
                if self.bot.guild_dict[guild.id]['configure_dict'].get('exraid', {}).get('permissions', 'everyone') == "everyone" or (self.bot.guild_dict[guild.id]['configure_dict'].get('exraid', {}).get('permissions', 'everyone') == "same" and rc_dict[channelid]['report_channel'] == channel.id):
                    exraid_channel = self.bot.get_channel(channelid)
                    if exraid_channel.mention != '#deleted-channel':
                        exraidcount += 1
                        exraidlist += (('\n**' + str(exraidcount)) + '.**   ') + exraid_channel.mention
                        exraid_dict[str(exraidcount)] = exraid_channel
        invite_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/eggs/EX.png?cache=1')
        invite_embed.add_field(name=_('**New Invite**'), value=f"Meowth! I'll help you gain access to an EX Raid channel!\n\nThe following {str(exraidcount)} EX Raids have been reported:\n{exraidlist}\n\nReply with **the number** (1, 2, etc) of the EX Raid you have been invited to. If none of them match your invite, reply with **cancel** and report it with **!exraid**", inline=False)
        invite_embed.set_footer(text=_('Inviting @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        while True:
            async with ctx.typing():
                if exraidcount == 0:
                    error = _("there are no EX raids. Report one with **!exraid**")
                    break
                if exraid_choice and int(exraid_choice) <= exraidcount and exraid_choice > 0:
                    exraid_channel = exraid_dict[str(int(exraid_choice))]
                    await self._invite(ctx, exraid_channel)
                    return
                else:
                    def check(reply):
                        if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                            return True
                        else:
                            return False
                    choice_wait = await channel.send(embed=invite_embed)
                    try:
                        choice_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        choice_msg = None
                    await utils.safe_delete(choice_wait)
                    if not choice_msg:
                        error = _("took too long to respond")
                        break
                    elif choice_msg.clean_content.lower() == "cancel" or choice_msg.clean_content.lower() == "n":
                        error = _("cancelled the invite")
                        await utils.safe_delete(choice_msg)
                        break
                    elif not choice_msg.content.isdigit() or int(choice_msg.content) > exraidcount:
                        error = _("entered something invalid")
                        await utils.safe_delete(choice_msg)
                        break
                    elif choice_msg:
                        exraid_choice = choice_msg.clean_content
                        exraid_channel = exraid_dict[str(int(exraid_choice))]
                    await utils.safe_delete(choice_msg)
                    break
        if not error:
            await self._invite(ctx, exraid_channel)
            return
        else:
            invite_embed.clear_fields()
            invite_embed.add_field(name=_('**Invite Cancelled**'), value=_("Meowth! Your invite has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=invite_embed, delete_after=10)
            await utils.safe_delete(message)

    async def _invite(self, ctx, exraid_channel):
        bot = ctx.bot
        channel = ctx.channel
        author = ctx.author
        guild = ctx.guild
        overwrite = discord.PermissionOverwrite()
        overwrite.send_messages = True
        overwrite.read_messages = True
        try:
            await exraid_channel.set_permissions(author, overwrite=overwrite)
        except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.InvalidArgument):
            pass
        invite_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/eggs/EX.png?cache=1')
        invite_embed.add_field(name=_('**New Invite**'), value=f"Meowth! Alright {author.mention}, you can now send messages in {exraid_channel.mention}! Make sure you let the trainers in there know if you can make it to the EX Raid!'", inline=False)
        exraidmsg = await channel.send(embed=invite_embed, delete_after=30)
        maybe_command = self.bot.get_command("interested")
        ctx.message.channel, ctx.channel = exraid_channel, exraid_channel
        await maybe_command.invoke(ctx)
        await asyncio.sleep(30)
        await utils.safe_delete(exraidmsg)

    @commands.group(aliases=['event'], case_insensitive=True, invoke_without_command=True)
    @checks.allowmeetupreport()
    async def meetup(self, ctx, *, location:commands.clean_content(fix_channel_mentions=True)=""):
        """Report an upcoming event.

        Usage: !meetup [location]
        Meowth will insert the details into a
        Google maps link and post the link to the same channel the report was made in.

        Finally, Meowth will create a separate channel for the report, for the purposes of organizing the event."""
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        error = False
        can_manage = ctx.channel.permissions_for(ctx.author).manage_channels
        raid_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/meetup.png?cache=1')
        raid_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        while True:
            async with ctx.typing():
                if location:
                    new_channel = await self._meetup(ctx, location)
                    ctx.raid_channel = new_channel
                    return
                else:
                    def check(reply):
                        if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                            return True
                        else:
                            return False
                    raid_embed.add_field(name=_('**New Meetup Report**'), value=_("Meowth! I'll help you report a community meetup!\n\nWhat's the location of the event? You can reply with **cancel** to stop anytime."), inline=False)
                    location_wait = await channel.send(embed=raid_embed)
                    try:
                        location_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        location_msg = None
                    await utils.safe_delete(location_wait)
                    if not location_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(location_msg)
                    if location_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif location_msg:
                        location = location_msg.clean_content
        if not error:
            new_channel = await self._meetup(ctx, location)
            ctx.raid_channel = new_channel
            return
        else:
            raid_embed.clear_fields()
            raid_embed.add_field(name=_('**Meetup Report Cancelled**'), value=_("Meowth! Your report has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=raid_embed, delete_after=10)
            if not message.embeds:
                await utils.safe_delete(message)

    async def _meetup(self, ctx, location):
        if "train" in str(ctx.command):
            meetup_type = "train"
            meetup_dict = "raidtrain_dict"
        else:
            meetup_type = "meetup"
            meetup_dict = "meetup_dict"
        if not ctx.prefix:
            prefix = self.bot._get_prefix(self.bot, ctx.message)
            ctx.prefix = prefix[-1]
        message = ctx.message
        channel = message.channel
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))).strftime(_('%I:%M %p (%H:%M)'))
        help_reaction = self.bot.custom_emoji.get('raid_info', u'\U00002139\U0000fe0f')
        maybe_reaction = self.bot.custom_emoji.get('raid_maybe', u'\U00002753')
        omw_reaction = self.bot.custom_emoji.get('raid_omw', u'\U0001f3ce\U0000fe0f')
        here_reaction = self.bot.custom_emoji.get('raid_here', u'\U0001F4CD')
        cancel_reaction = self.bot.custom_emoji.get('raid_cancel', u'\U0000274C')
        report_emoji = self.bot.custom_emoji.get('meetup_report', u'\U0001F4E2')
        list_emoji = self.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f')
        react_list = [maybe_reaction, omw_reaction, here_reaction, cancel_reaction]
        raid_details = location.strip()
        raid_gmaps_link = utils.create_gmaps_query(self.bot, raid_details, message.channel, type="meetup")
        raid_channel = await self.create_raid_channel(ctx, "EX", raid_details, meetup_type)
        if not raid_channel:
            return
        raid_img_url = f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/{meetup_type}.png?cache=1"
        raid_embed = discord.Embed(title=f"Meowth! Click here for directions to the {meetup_type}!", description="", url=raid_gmaps_link, colour=message.guild.me.colour)
        raid_embed.add_field(name=f"**{meetup_type.title()} Title:**", value=f"Set with **{ctx.prefix}{meetup_type} title**", inline=True)
        raid_embed.add_field(name=f"**{meetup_type.title()} Location:**", value=raid_details, inline=True)
        raid_embed.add_field(name=f"**{meetup_type.title()} Starts:**", value=f"Set with **{ctx.prefix}{meetup_type} start**", inline=True)
        raid_embed.add_field(name=f"**{meetup_type.title()} Ends:**", value=f"Set with **{ctx.prefix}{meetup_type} end**", inline=True)
        raid_embed.set_footer(text=f"Reported by @{ctx.author.display_name} - {timestamp}", icon_url=message.author.avatar_url_as(format=None, static_format='jpg', size=32))
        raid_embed.set_thumbnail(url=raid_img_url)
        raid_embed.set_author(name=f"{meetup_type.title()} Report", icon_url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/{meetup_type}.png?cache=1")
        ctx.raidreport = await channel.send(content=f"Meowth! {meetup_type.title()} reported by {message.author.mention}! Details: {raid_details}. Coordinate in {raid_channel.mention}\n\nUse {maybe_reaction} if interested, {omw_reaction} if coming, {here_reaction} if there, {cancel_reaction} to cancel, {report_emoji} to report new, or {list_emoji} to list all meetups!", embed=raid_embed)
        await asyncio.sleep(1)
        raidmsg = f"Meowth! {meetup_type.title()} reported by {message.author.mention} in {message.channel.mention}! Details: {raid_details}. Coordinate here!\n\nClick the {help_reaction} to get help on commands, {maybe_reaction} if interested, {omw_reaction} if coming, {here_reaction} if there, or {cancel_reaction} to cancel!\n\nThis channel will be deleted five minutes after the timer expires."
        raid_message = await raid_channel.send(content=raidmsg, embed=raid_embed)
        await utils.add_reaction(raid_message, help_reaction)
        for reaction in react_list:
            await asyncio.sleep(0.25)
            await utils.add_reaction(raid_message, reaction)
            await asyncio.sleep(0.25)
            await utils.add_reaction(ctx.raidreport, reaction)
        await utils.add_reaction(ctx.raidreport, report_emoji)
        await utils.add_reaction(ctx.raidreport, list_emoji)
        await raid_message.pin()
        self.bot.guild_dict[message.guild.id][meetup_dict][raid_channel.id] = {
            'report_channel':channel.id,
            'report_guild':message.guild.id,
            'report_author':message.author.id,
            'trainer_dict': {},
            'report_time':time.time(),
            'exp': time.time() + (((60 * 60) * 24) * self.bot.raid_info['raid_eggs']['EX']['hatchtime']),
            'manual_timer': False,
            'active': True,
            'raid_message':raid_message.id,
            'raid_report':ctx.raidreport.id,
            'raid_embed':raid_embed,
            'report_message':message.id,
            'address': raid_details,
            'type': 'egg',
            'pokemon': '',
            'egg_level': 'EX',
            'meetup': {'start':None, 'end':None, 'channel_name':utils.sanitize_channel_name(raid_details).lower()}
        }
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[raid_channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
        timerset_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_date.png?cache=1")
        timerset_embed.add_field(name=f"**Channel Timer**", value=f"If you can, set the time that the {meetup_type} starts and ends with **{ctx.prefix}{meetup_type} start <date and time>** and **{ctx.prefix}{meetup_type} end <date and time>**. You can also set the title of the {meetup_type} using **{ctx.prefix}{meetup_type} title <title>**.\n\nThe current timer is ***unknown***.")
        timerset_msg = await raid_channel.send(f"Meowth! Hey {ctx.author.mention}!", embed=timerset_embed)
        ctx.bot.guild_dict[message.guild.id][meetup_dict][raid_channel.id]['timerset_msg'] = timerset_msg.id
        self.bot.loop.create_task(self.expiry_check(raid_channel))
        return raid_channel

    @meetup.command(name="title")
    @checks.meetupchannel()
    async def meetup_title(self, ctx, *, title):
        meetup_dict = await utils.get_report_dict(ctx.bot, ctx.channel)
        meetup_type = "train" if meetup_dict == "raidtrain_dict" else "meetup"
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        error = False
        can_manage = ctx.channel.permissions_for(ctx.author).manage_channels
        try:
            report_channel = self.bot.get_channel(self.bot.guild_dict[guild.id][meetup_dict][channel.id]['report_channel'])
        except KeyError:
            return
        oldraidmsg = await ctx.channel.fetch_message(self.bot.guild_dict[guild.id][meetup_dict][channel.id]['raid_message'])
        oldreportmsg = await report_channel.fetch_message(self.bot.guild_dict[guild.id][meetup_dict][channel.id]['raid_report'])
        report_message = self.bot.guild_dict[guild.id][meetup_dict][channel.id]['report_message']
        oldembed = oldraidmsg.embeds[0]
        newembed = discord.Embed(title=oldembed.title, description=oldembed.description, url=oldembed.url, colour=oldembed.colour)
        for field in oldembed.fields:
            newembed.add_field(name=field.name, value=field.value, inline=field.inline)
        index = 0
        for field in newembed.fields:
            if f"**{meetup_type.title()} Title:**" in field.name:
                newembed.set_field_at(index, name=f"**{meetup_type.title()} Title:**", value=title, inline=field.inline)
                break
            else:
                index += 1
        newembed.set_footer(text=oldembed.footer.text, icon_url=oldembed.footer.icon_url)
        newembed.set_thumbnail(url=f"{oldembed.thumbnail.url.split('&report_message=')[0]}&report_message={report_message}&raid_report={oldreportmsg.id}")
        newembed.set_author(name=oldembed.author.name, icon_url=oldembed.author.icon_url)
        try:
            await oldraidmsg.edit(embed=newembed, content=oldraidmsg.content)
        except:
            pass
        try:
            await oldreportmsg.edit(embed=newembed, content=oldreportmsg.content)
        except:
            pass
        self.bot.guild_dict[ctx.guild.id][meetup_dict][ctx.channel.id]['raid_message'] = oldraidmsg.id
        self.bot.guild_dict[ctx.guild.id][meetup_dict][ctx.channel.id]['raid_report'] = oldreportmsg.id
        self.bot.guild_dict[ctx.guild.id][meetup_dict][ctx.channel.id]['meetup']['title'] = title
        channel_name = self.bot.guild_dict[ctx.guild.id][meetup_dict][ctx.channel.id]['meetup']['channel_name']
        if can_manage or meetup_type == "train":
            if ctx.invoked_with != "title":
                self.bot.guild_dict[message.guild.id][meetup_dict][ctx.channel.id]['meetup']['channel_name'] = utils.sanitize_channel_name(title).lower()
                raid_channel_name = await self.edit_channel_name(channel)
                return await ctx.channel.edit(name=raid_channel_name)
            question = await ctx.channel.send(f"Would you like to change the channel name to {ctx.channel.name.replace('train-', '').replace('meetup-', '').replace(channel_name, '')}{meetup_type.lower()}-{title.lower()}?")
            try:
                timeout = False
                res, reactuser = await utils.ask(self.bot, question, ctx.author.id)
            except TypeError:
                timeout = True
            if timeout:
                return
            if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', u'\U0000274e'):
                await utils.safe_delete(question)
                return
            elif res.emoji == self.bot.custom_emoji.get('answer_yes', u'\U00002705'):
                self.bot.guild_dict[message.guild.id][meetup_dict][message.channel.id]['meetup']['channel_name'] = utils.sanitize_channel_name(title).lower()
                raid_channel_name = await self.edit_channel_name(channel)
                await utils.safe_delete(question)
            await ctx.channel.edit(name=raid_channel_name)

    @meetup.command(name="start")
    @checks.meetupchannel()
    async def meetup_start(self, ctx, *, timer):
        await ctx.invoke(self.bot.get_command("starttime"), start_time=timer)

    @meetup.command(name="end")
    @checks.meetupchannel()
    async def meetup_end(self, ctx, *, timer):
        await ctx.invoke(self.bot.get_command("timerset"), timer=timer)

    @meetup.command(aliases=['expire', 'delete'], name='reset')
    @checks.allowmeetupreport()
    @checks.is_mod()
    async def reset_meetups(self, ctx, *, channel:discord.TextChannel=None):
        await self.raid_reset(ctx, channel, type='meetup')

    @commands.group(case_insensitive=True, invoke_without_command=True, aliases=['chain'])
    @checks.allowtrainreport()
    async def train(self, ctx, *, channel_or_gym=None):
        """Report an ongoing raid train.

        Usage: !train [channel or location]
        Starts a raid train if used in a reporting channel. Continues
        a raid train if used in a raid channel."""
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        error = False
        train_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/train.png?cache=1')
        train_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        active_trains = []
        train_msg = ""
        for raid_channel in self.bot.guild_dict[guild.id]['raidchannel_dict']:
            for trainer in self.bot.guild_dict[guild.id]['raidchannel_dict'][raid_channel]['trainer_dict']:
                if self.bot.guild_dict[guild.id]['raidchannel_dict'][raid_channel]['trainer_dict'][trainer].get('train', False):
                    raid_channel = self.bot.get_channel(raid_channel)
                    if raid_channel:
                        active_trains.append(raid_channel.mention)
                        break
        def check(reply):
            if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                return True
            else:
                return False
        if active_trains:
            train_msg = "\n\nThere are active trains that you can join in the following channels:\n{active_trains}\n\n".format(active_trains=('\n').join(active_trains))
        while True:
            async with ctx.typing():
                if not channel_or_gym:
                    train_embed.add_field(name=_('**New Raid Train Report**'), value=f"Meowth! I'll help you report a raid train!\n\nFirst, I'll need to know what **channel of location** you'd like to start the raid train at. Reply with the name of a **location** or **channel mention**.{train_msg}You can reply with **cancel** to stop anytime.", inline=False)
                    channel_or_gym_wait = await channel.send(embed=train_embed)
                    try:
                        channel_or_gym_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        channel_or_gym_msg = None
                    await utils.safe_delete(channel_or_gym_wait)
                    if not channel_or_gym_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(channel_or_gym_msg)
                    if channel_or_gym_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    else:
                        channel_or_gym = channel_or_gym_msg.content.lower()
                converter = commands.TextChannelConverter()
                location = ""
                if not location:
                    try:
                        channel_or_gym = await converter.convert(ctx, channel_or_gym)
                    except:
                        pass
                if isinstance(channel_or_gym, discord.TextChannel):
                    if channel_or_gym == ctx.channel:
                        error = _("entered this channel")
                        break
                    if channel_or_gym.id in self.bot.guild_dict[ctx.guild.id]['raidchannel_dict']:
                        location = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][channel_or_gym.id]['address']
                if not location:
                    gym_matching_cog = self.bot.cogs.get('GymMatching')
                    gym_info = ""
                    if gym_matching_cog and not location:
                        gym_info, location, gym_url = await gym_matching_cog.get_poi_info(ctx, str(channel_or_gym), "raid", dupe_check=False)
                    if location:
                        channel_or_gym = location
                    gym_search = str(channel_or_gym)
                    for raid_channel in self.bot.guild_dict[ctx.guild.id]['raidchannel_dict']:
                        raid_channel = self.bot.get_channel(raid_channel)
                        raid_address = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][raid_channel.id]['address']
                        raid_type = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][raid_channel.id]['type']
                        raid_level = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][raid_channel.id]['egg_level']
                        if str(gym_search).lower() == str(raid_address).lower() and raid_type != "exraid" and raid_level != "EX":
                            channel_or_gym = raid_channel
                            break
                    if not channel_or_gym and not location:
                        error = _("entered an invalid location or channel")
                        break
                if checks.check_raidreport(ctx) or checks.check_meetupreport(ctx):
                    train_embed.clear_fields()
                    train_embed.add_field(name=_('**New Raid Train Report**'), value=f"Great! Now, would you like to create a new channel to manage this raid train, or move between current raid channels? Reply with **channel** to create a channel, **current** to keep coordination in raid channels, or **cancel** to stop anytime.", inline=False)
                    channel_wait = await channel.send(embed=train_embed)
                    try:
                        channel_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        channel_msg = None
                    await utils.safe_delete(channel_wait)
                    if not channel_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(channel_msg)
                    if channel_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif channel_msg.clean_content.lower() == "current":
                        if not isinstance(channel_or_gym, discord.TextChannel):
                            error = _("entered a location without a raid channel")
                            break
                        train_embed.clear_fields()
                        train_embed.add_field(name=_('**New Raid Train Report**'), value=f"Great! Now, reply with your **party and team counts** `Ex: 5 2m 2v 1i` or reply with **1** if it's just you. You can reply with **cancel** to stop anytime.", inline=False)
                        party_wait = await channel.send(embed=train_embed)
                        try:
                            party_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            party_msg = None
                        await utils.safe_delete(party_wait)
                        if not party_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(party_msg)
                        if party_msg.clean_content.lower() == "cancel":
                            error = _("cancelled the report")
                            break
                        elif party_msg:
                            teamcounts = party_msg.clean_content.lower()
                            if not teamcounts.split()[0].isdigit():
                                error = _("entered an invalid party count")
                                break
                            ctx.message.channel, ctx.channel = channel_or_gym, channel_or_gym
                            await self._rsvp(ctx, "coming", teamcounts)
                            train_embed.clear_fields()
                            train_embed.add_field(name=_('**New Raid Train Report**'), value=_("Meowth! Your raid train has been started in {raid_channel}").format(raid_channel=channel_or_gym.mention), inline=False)
                            confirmation = await channel.send(embed=train_embed, delete_after=10)
                            await utils.safe_delete(message)
                            await asyncio.sleep(1)
                            self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][channel_or_gym.id]['trainer_dict'][author.id]['train'] = True
                            return
                    elif channel_msg.clean_content.lower() == "channel":
                        return await self._train_channel(ctx, channel_or_gym)
                    else:
                        error = _("entered something invalid")
                        break
                elif checks.check_raidchannel(ctx) and not checks.check_exraidchannel(ctx):
                    if not isinstance(channel_or_gym, discord.TextChannel):
                        error = _("entered a location without a raid channel")
                        break
                    train_emoji = self.bot.custom_emoji.get('train_emoji', u'\U0001F682')
                    train_msg = await ctx.send(f"Meowth! {ctx.author.mention} wants to keep this **raid train** moving in {channel_or_gym.mention}!\n\nReact to this message with {train_emoji} to automatically RSVP in {channel_or_gym.mention} with your current party.")
                    await utils.add_reaction(train_msg, train_emoji)
                    teamcounts = ""
                    def get_teamcounts(raid_channel, trainer, lobby):
                        total = lobby[trainer]['count']
                        mystic = lobby[trainer]['party']['mystic']
                        valor = lobby[trainer]['party']['valor']
                        instinct = lobby[trainer]['party']['instinct']
                        unknown = lobby[trainer]['party']['unknown']
                        return f"{total} {mystic}m {valor}v {instinct}i {unknown}u"
                    for trainer in self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][ctx.channel.id]['trainer_dict']:
                        if trainer == ctx.author.id:
                            teamcounts = get_teamcounts(ctx.channel, trainer, self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][ctx.channel.id]['trainer_dict'])
                            break
                    if not teamcounts:
                        for trainer in self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][ctx.channel.id].get('lobby', {}).get('starting_dict', {}):
                            if trainer == ctx.author.id:
                                teamcounts = get_teamcounts(ctx.channel, trainer, self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][ctx.channel.id].get('lobby', {}).get('starting_dict', {}))
                                break
                    if not teamcounts:
                        for lobby in self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][ctx.channel.id].get('battling', []):
                            for trainer in lobby['starting_dict']:
                                if trainer == ctx.author.id:
                                    teamcounts = get_teamcounts(ctx.channel, trainer, lobby['starting_dict'])
                                    break
                    if not teamcounts:
                        for lobby in self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][ctx.channel.id].get('completed', []):
                            for trainer in lobby['starting_dict']:
                                if trainer == ctx.author.id:
                                    teamcounts = get_teamcounts(ctx.channel, trainer, lobby['starting_dict'])
                                    break
                    if not teamcounts:
                        teamcounts = "1"
                    trainer_set = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][channel_or_gym.id]['trainer_dict'].setdefault(author.id, {}).setdefault('train', True)
                    self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][channel_or_gym.id]['trainer_dict'][author.id]['train'] = True
                    channel_set = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][ctx.channel.id].setdefault('next_trains', {}).setdefault(train_msg.id, {})
                    self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][ctx.channel.id]['next_trains'][train_msg.id] = {'author':ctx.author.id, 'channel':channel_or_gym.id}
                    ctx.message.channel, ctx.channel = channel_or_gym, channel_or_gym
                    return await self._rsvp(ctx, "coming", teamcounts)
        if error:
            train_embed.clear_fields()
            train_embed.add_field(name=_('**Raid Report Cancelled**'), value=_("Meowth! Your report has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=train_embed, delete_after=10)
            if not message.embeds:
                await utils.safe_delete(message)

    @train.command(name="channel")
    @checks.allowtrainreport()
    async def train_channel(self, ctx, *, channel_or_gym):
        """Report a new raid train channel"""
        await self._train_channel(ctx, channel_or_gym)

    async def _train_channel(self, ctx, channel_or_gym):
        location = ""
        raidhour_check = getattr(ctx, "raidhour", False)
        help_reaction = self.bot.custom_emoji.get('raid_info', u'\U00002139\U0000fe0f')
        if isinstance(channel_or_gym, discord.TextChannel):
            if channel_or_gym.id in self.bot.guild_dict[ctx.guild.id]['raidchannel_dict']:
                location = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][channel_or_gym.id]['address']
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        gym_info = ""
        if not location and gym_matching_cog:
            if raidhour_check:
                gym_info, location, gym_url = await gym_matching_cog.get_poi_info(ctx, str(channel_or_gym), "raid", dupe_check=False, autocorrect=False)
            else:
                gym_info, location, gym_url = await gym_matching_cog.get_poi_info(ctx, str(channel_or_gym), "raid", dupe_check=False)
        if location:
            channel_or_gym = location
        train_location = str(channel_or_gym)
        train_channel = await self._meetup(ctx, train_location)
        if train_channel:
            managers = self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'][train_channel.id].get('managers', [])
            manager_embed = discord.Embed(colour=ctx.guild.me.colour).set_author(name=_('Raid Manager Help')).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/train.png?cache=1')
            manager_embed.add_field(name=f"{ctx.prefix}train start <date and time>", value=f"Sets the train start time. Example: `!train start 6pm`", inline=False)
            manager_embed.add_field(name=f"{ctx.prefix}train end <date and time>", value=f"Sets the train end time. Example: `!train end 7pm`", inline=False)
            manager_embed.add_field(name=f"{ctx.prefix}train manager <user @mention>", value=f"Once you become a train manager, you can promote new train managers using this command. Example: `!train manager @{ctx.guild.me.display_name}`", inline=False)
            manager_embed.add_field(name=f"{ctx.prefix}train route <gym list>", value=f"If you have a planned route, you can set it using this command. Example: `!train route Hershey Park, Liberty Park`", inline=False)
            manager_embed.add_field(name=f"{ctx.prefix}next [gym name]", value=f"Alert the channel that you are going to a new gym. Example: `!next Hershey Park`. If a route is set, train will move to next gym without needing a gym name", inline=False)
            manager_embed.add_field(name=f"{ctx.prefix}starting", value=f"Alert the channel that you are starting at the current location", inline=False)
            await ctx.author.send(embed=manager_embed, delete_after=3600)
            train_embed = discord.Embed(colour=ctx.guild.me.colour).set_author(name=f"Raid Train Instructions").set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/train.png?cache=1')
            train_embed.add_field(name="**Assigning Managers**", value=f"Nominate yourself or other trainers using **{ctx.prefix}train nominate [@mention]**", inline=False)
            train_embed.add_field(name="**Directing Train**", value=f"Direct the train using **{ctx.prefix}next vote**", inline=False)
            train_embed.add_field(name="**Other Commands**", value=f"Use {help_reaction} above to see available commands", inline=False)
            await train_channel.send(f"{ctx.author.mention}, you are the current manager of this train! Check your DMs for manager instructions! Everyone else, you can control the channel using these instructions:", embed=train_embed)
            self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'][train_channel.id]['managers'] = [ctx.author.id]
            self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'][train_channel.id]['meetup']['raid'] = True
            utcnow = (datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
            to_raidend = 24*60*60 - ((utcnow-utcnow.replace(hour=21, minute=0, second=0, microsecond=0)).seconds)
            self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'][train_channel.id]['exp'] = time.time() + to_raidend
            self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'][train_channel.id]['meetup']['end'] = datetime.datetime.fromtimestamp(time.time() + to_raidend)
            self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'][train_channel.id]['meetup']['history'] = [train_location]
            raid_found = False
            for channel in self.bot.guild_dict[ctx.guild.id]['raidchannel_dict']:
                channel_address = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][channel]['address']
                channel_level = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][channel]['egg_level']
                channel_type = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][channel]['type']
                if channel_address == train_location and channel_level != "EX" and channel_type != "exraid":
                    raid_channel = self.bot.get_channel(channel)
                    await raid_channel.send(f"A raid train channel has chosen this raid as its next raid! You can join them in {ctx.channel.mention}")
                    try:
                        timer_set = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][channel]['manual_timer']
                        raid_timer = ""
                        raid_message = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][channel]['raid_message']
                        moveset = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][channel].get('moves', None)
                        raid_message = await raid_channel.fetch_message(raid_message)
                        raid_embed = raid_message.embeds[0]
                        while len(raid_embed.fields) > 2:
                            raid_embed.remove_field(-1)
                        if moveset:
                            moveset = moveset.split(' / ')
                            for index, m in enumerate(moveset):
                                if m.lower() in self.bot.move_info.keys():
                                    moveset[index] = f"{m} {utils.type_to_emoji(self.bot, self.bot.move_info[m.lower()]['type'])}"
                            raid_embed.add_field(name=f"**Moveset:**", value=(' / ').join([x.title() for x in moveset]))
                        if timer_set:
                            raid_timer = await self.print_raid_timer(raid_channel)
                        await train_channel.send(f"Meowth! I found this raid at **{train_location}**! {raid_timer}", embed=raid_embed)
                        raid_found = True
                    except:
                        pass
                    break
            if not raid_found:
                for report in self.bot.guild_dict[ctx.guild.id]['pokealarm_dict']:
                    report_address = self.bot.guild_dict[ctx.guild.id]['pokealarm_dict'][report]['gym']
                    report_level = self.bot.guild_dict[ctx.guild.id]['pokealarm_dict'][report]['level']
                    report_type = self.bot.guild_dict[ctx.guild.id]['pokealarm_dict'][report]['reporttype']
                    raidexp = self.bot.guild_dict[ctx.guild.id]['pokealarm_dict'][report]['raidexp']
                    moveset = self.bot.guild_dict[ctx.guild.id]['pokealarm_dict'][report].get('moves', None)
                    if report_address.lower() == train_location.lower() and report_level != "EX" and report_type != "exraid":
                        raid_embed = await self.make_raid_embed(ctx, self.bot.guild_dict[ctx.guild.id]['pokealarm_dict'][report], raidexp)
                        while len(raid_embed.fields) > 2:
                            raid_embed.remove_field(-1)
                        if moveset:
                            moveset = moveset.split(' / ')
                            for index, m in enumerate(moveset):
                                if m.lower() in self.bot.move_info.keys():
                                    moveset[index] = f"{m} {utils.type_to_emoji(self.bot, self.bot.move_info[m.lower()]['type'])}"
                            raid_embed.add_field(name=f"**Moveset:**", value=(' / ').join([x.title() for x in moveset]))
                        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                        raid_timer = (now + datetime.timedelta(minutes=float(raidexp))).strftime(_('%B %d at %I:%M %p (%H:%M)'))
                        await train_channel.send(f"Meowth! I found this raid at **{train_location}**! {'Hatches' if report_type == 'egg' else 'Expires'}: {raid_timer}", embed=raid_embed)
            return train_channel

    @train.command(name="title")
    @checks.trainchannel()
    async def train_title(self, ctx, *, title):
        """Set raid train channel title"""
        can_manage = ctx.channel.permissions_for(ctx.author).manage_channels or ctx.author.id in self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'].get(ctx.channel.id, {}).get('managers', [])
        if not can_manage:
            return await ctx.send(f"**{ctx.prefix}train {ctx.invoked_with}** can only be used by managers. Use **{ctx.prefix}train nominate [@mention]** to nominate yourself or @mention!", delete_after=60)
        await ctx.invoke(self.bot.get_command("meetup title"), title=title)

    @train.command(name="start")
    @checks.trainchannel()
    async def train_start(self, ctx, *, timer):
        """Set raid train channel start time"""
        can_manage = ctx.channel.permissions_for(ctx.author).manage_channels or ctx.author.id in self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'].get(ctx.channel.id, {}).get('managers', [])
        if not can_manage:
            return await ctx.send(f"**{ctx.prefix}train {ctx.invoked_with}** can only be used by managers. Use **{ctx.prefix}train nominate [@mention]** to nominate yourself or @mention!", delete_after=60)
        await ctx.invoke(self.bot.get_command("starttime"), start_time=timer)

    @train.command(name="end")
    @checks.trainchannel()
    async def train_end(self, ctx, *, timer):
        """Set raid train channel end time"""
        can_manage = ctx.channel.permissions_for(ctx.author).manage_channels or ctx.author.id in self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'].get(ctx.channel.id, {}).get('managers', [])
        if not can_manage:
            return await ctx.send(f"**{ctx.prefix}train {ctx.invoked_with}** can only be used by managers. Use **{ctx.prefix}train nominate [@mention]** to nominate yourself or @mention!", delete_after=60)
        await ctx.invoke(self.bot.get_command("timerset"), timer=timer)

    @commands.group(name="next", hidden=True, invoke_without_command=True)
    @checks.trainchannel()
    async def train_next_parent(self, ctx, *, channel_or_gym=''):
        """Proceed to next train location"""
        can_manage = ctx.channel.permissions_for(ctx.author).manage_channels or ctx.author.id in self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'].get(ctx.channel.id, {}).get('managers', [])
        vote = getattr(ctx, "vote", False)
        if not can_manage and not vote:
            return await ctx.invoke(self.bot.get_command("next vote"))
        await ctx.invoke(self.bot.get_command("train next"), channel_or_gym=channel_or_gym)

    @train_next_parent.command(name="vote")
    @checks.trainchannel()
    async def next_vote(self, ctx, *, gyms=None):
        """Vote on next train location"""
        emoji_dict = {0: u'\U00000030\U0000fe0f\U000020e3', 1: u'\U00000031\U0000fe0f\U000020e3', 2: u'\U00000032\U0000fe0f\U000020e3', 3: u'\U00000033\U0000fe0f\U000020e3', 4: u'\U00000034\U0000fe0f\U000020e3', 5: u'\U00000035\U0000fe0f\U000020e3', 6: u'\U00000036\U0000fe0f\U000020e3', 7: u'\U00000037\U0000fe0f\U000020e3', 8: u'\U00000038\U0000fe0f\U000020e3', 9: u'\U00000039\U0000fe0f\U000020e3', 10: u'\U0001f51f'}
        cancel_emoji = self.bot.custom_emoji.get('trade_stop', u'\U000023f9\U0000fe0f')
        options_list = []
        manager_list = []
        trainer_list = []
        result_dict = {}
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        error = False
        train_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/train.png?cache=1')
        train_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=ctx.author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=ctx.author.avatar_url_as(format=None, static_format='jpg', size=32))
        def check(reply):
            if reply.author is not ctx.guild.me and reply.channel.id == ctx.channel.id and reply.author == ctx.message.author:
                return True
            else:
                return False
        if gyms:
            options_list = gyms.split(',')
            options_list = [x.strip() for x in options_list]
            vote_list = options_list
        else:
            while True:
                async with ctx.typing():
                    train_embed.add_field(name=_('**New Raid Train Vote**'), value=f"Meowth! I'll help you vote on the next train location!\n\nReply with a comma separated list of up to ten locations to vote on. You can reply with **cancel** to stop anytime.", inline=False)
                    vote_list_wait = await ctx.send(embed=train_embed)
                    try:
                        vote_list_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        vote_list_msg = None
                    await utils.safe_delete(vote_list_wait)
                    if not vote_list_msg:
                        train_embed.clear_fields()
                        train_embed.add_field(name=_('**Train Vote Cancelled**'), value=_("Meowth! Your vote has been cancelled because you entered took too long to respond! Retry when you're ready."), inline=False)
                        return await ctx.send(embed=train_embed, delete_after=10)
                    else:
                        await utils.safe_delete(vote_list_msg)
                    if vote_list_msg.clean_content.lower() == "cancel":
                        train_embed.clear_fields()
                        train_embed.add_field(name=_('**Train Vote Cancelled**'), value=_("Meowth! Your vote has been cancelled because you cancelled the report! Retry when you're ready."), inline=False)
                        return await ctx.send(embed=train_embed, delete_after=10)
                    else:
                        vote_list = vote_list_msg.content.lower().split(',')
                        vote_list = [x.strip() for x in vote_list]
                        if len(vote_list) > 10:
                            train_embed.clear_fields()
                            train_embed.add_field(name=_('**Train Vote Cancelled**'), value=_("Meowth! Your vote has been cancelled because you entered too many options! Retry when you're ready."), inline=False)
                            return await ctx.send(embed=train_embed, delete_after=10)
                        options_list = vote_list
                        break
        for trainer in self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'][ctx.channel.id]['trainer_dict']:
            user = ctx.guild.get_member(trainer)
            if not user:
                continue
            if sum(self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'][ctx.channel.id]['trainer_dict'][trainer]['status'].values()) == 0:
                continue
            trainer_list.append(user)
        for manager in self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'].get(ctx.channel.id, {}).get('managers', []):
            user = ctx.guild.get_member(manager)
            if not user:
                continue
            manager_list.append(user)
        vote_msg_content = ""
        for option, emoji in zip(vote_list, emoji_dict.values()):
            vote_msg_content += f"{emoji} - {option}\n"
        train_embed.clear_fields()
        train_embed.add_field(name=f"**Next Train Vote**", value=vote_msg_content)
        vote_message = await ctx.send(f"Trainers {(', ').join([x.mention for x in trainer_list])}! {ctx.author.mention} has asked for a vote for the next train location. Please vote using reactions below.\n\nCurrent managers {', '.join([x.mention for x in manager_list])} can react with {cancel_emoji} to cancel the vote.", embed=train_embed)
        for option, emoji in zip(vote_list, emoji_dict.keys()):
            await utils.add_reaction(vote_message, emoji_dict[emoji])
        await utils.add_reaction(vote_message, cancel_emoji)
        await asyncio.sleep(30)
        vote_message = await ctx.channel.fetch_message(vote_message.id)
        for index, reaction in enumerate(vote_message.reactions):
            if reaction.me and reaction.emoji != cancel_emoji:
                result_dict[index] = reaction.count
            elif reaction.emoji == cancel_emoji and reaction.count > 1:
                users = await reaction.users().flatten()
                for user in users:
                    can_manage = ctx.channel.permissions_for(user).manage_channels or user.id in self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'].get(ctx.channel.id, {}).get('managers', [])
                    if can_manage:
                        await utils.safe_delete(vote_message)
                        return await ctx.send("The vote has failed.")
        vote_winner = max(result_dict.keys(), key=(lambda key: result_dict[key]))
        vote_winner = options_list[vote_winner]
        ctx.vote = True
        await utils.safe_delete(vote_message)
        await ctx.invoke(self.bot.get_command('train next'), channel_or_gym=vote_winner)

    @train.command(name="vote")
    @checks.trainchannel()
    async def train_vote(self, ctx, *, gyms=None):
        """Vote on next train location"""
        return await ctx.invoke(self.bot.get_command('next vote'), gyms=gyms)

    @train.command(name="next")
    @checks.trainchannel()
    async def train_next(self, ctx, *, channel_or_gym=''):
        """Proceed to next train location"""
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        train_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/train.png?cache=1')
        train_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=ctx.author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=ctx.author.avatar_url_as(format=None, static_format='jpg', size=32))
        if channel_or_gym.lower() == "vote":
            return await ctx.invoke(self.bot.get_command('next vote'), gyms=None)
        can_manage = ctx.channel.permissions_for(ctx.author).manage_channels or ctx.author.id in self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'].get(ctx.channel.id, {}).get('managers', [])
        vote = getattr(ctx, "vote", False)
        if not can_manage and not vote:
            return await ctx.invoke(self.bot.get_command("next vote"), gyms=None)
        train_path = self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'][ctx.channel.id]['meetup'].setdefault('route', [])
        if train_path and not channel_or_gym:
            location, channel_or_gym = train_path[0], train_path[0]
            train_path.remove(location)
        else:
            if not channel_or_gym:
                def check(reply):
                    if reply.author is not ctx.guild.me and reply.channel.id == ctx.channel.id and reply.author == ctx.message.author:
                        return True
                    else:
                        return False
                while True:
                    async with ctx.typing():
                        train_embed.add_field(name=_('**New Raid Train Location**'), value=f"Meowth! I'll help you set the next train location!\n\nReply with the **location** you would like to move the train to. You can reply with **cancel** to stop anytime.", inline=False)
                        vote_list_wait = await ctx.send(embed=train_embed)
                        try:
                            vote_list_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            vote_list_msg = None
                        await utils.safe_delete(vote_list_wait)
                        if not vote_list_msg:
                            train_embed.clear_fields()
                            train_embed.add_field(name=_('**Train Location Cancelled**'), value=_("Meowth! Your vote has been cancelled because you entered took too long to respond! Retry when you're ready."), inline=False)
                            return await ctx.send(embed=train_embed, delete_after=10)
                        else:
                            await utils.safe_delete(vote_list_msg)
                        if vote_list_msg.clean_content.lower() == "cancel":
                            train_embed.clear_fields()
                            train_embed.add_field(name=_('**Train Location Cancelled**'), value=_("Meowth! Your vote has been cancelled because you cancelled the report! Retry when you're ready."), inline=False)
                            return await ctx.send(embed=train_embed, delete_after=10)
                        else:
                            channel_or_gym = vote_list_msg.clean_content
                            break
            converter = commands.TextChannelConverter()
            try:
                channel_or_gym = await converter.convert(ctx, channel_or_gym)
            except:
                location = ""
            if isinstance(channel_or_gym, discord.TextChannel):
                if channel_or_gym.id in self.bot.guild_dict[ctx.guild.id]['raidchannel_dict']:
                    location = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][channel_or_gym.id]['address']
        if not location:
            gym_matching_cog = self.bot.cogs.get('GymMatching')
            gym_info = ""
            if gym_matching_cog:
                gym_info, location, gym_url = await gym_matching_cog.get_poi_info(ctx, str(channel_or_gym), "raid", dupe_check=False)
        if location:
            channel_or_gym = location
        train_location = str(channel_or_gym)
        await ctx.invoke(self.bot.get_command("location new"), content=train_location)
        self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'][ctx.channel.id]['meetup'].setdefault('history', []).append(train_location)
        raid_found = False
        for channel in self.bot.guild_dict[ctx.guild.id]['raidchannel_dict']:
            channel_address = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][channel]['address']
            channel_level = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][channel]['egg_level']
            channel_type = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][channel]['type']
            moveset = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][channel].get('moves', None)
            if channel_address == train_location and channel_level != "EX" and channel_type != "exraid":
                raid_channel = self.bot.get_channel(channel)
                await raid_channel.send(f"A raid train channel has chosen this raid as its next raid! You can join them in {ctx.channel.mention}")
                try:
                    timer_set = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][channel]['manual_timer']
                    raid_timer = ""
                    raid_message = self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'][channel]['raid_message']
                    raid_message = await raid_channel.fetch_message(raid_message)
                    raid_embed = raid_message.embeds[0]
                    while len(raid_embed.fields) > 2:
                        raid_embed.remove_field(-1)
                    if moveset:
                        moveset = moveset.split(' / ')
                        for index, m in enumerate(moveset):
                            if m.lower() in self.bot.move_info.keys():
                                moveset[index] = f"{m} {utils.type_to_emoji(self.bot, self.bot.move_info[m.lower()]['type'])}"
                        raid_embed.add_field(name=f"**Moveset:**", value=(' / ').join([x.title() for x in moveset]))
                    if timer_set:
                        raid_timer = await self.print_raid_timer(raid_channel)
                    await ctx.send(f"Meowth! I found this raid at **{train_location}**! {raid_timer}", embed=raid_embed)
                    raid_found = True
                except:
                    pass
        if not raid_found:
            for report in self.bot.guild_dict[ctx.guild.id]['pokealarm_dict']:
                report_address = self.bot.guild_dict[ctx.guild.id]['pokealarm_dict'][report]['gym']
                report_level = self.bot.guild_dict[ctx.guild.id]['pokealarm_dict'][report]['level']
                report_type = self.bot.guild_dict[ctx.guild.id]['pokealarm_dict'][report]['reporttype']
                raidexp = self.bot.guild_dict[ctx.guild.id]['pokealarm_dict'][report]['raidexp']
                moveset = self.bot.guild_dict[ctx.guild.id]['pokealarm_dict'][report].get('moves', None)
                if report_address.lower() == train_location.lower() and report_level != "EX" and report_type != "exraid":
                    raid_embed = await self.make_raid_embed(ctx, self.bot.guild_dict[ctx.guild.id]['pokealarm_dict'][report], raidexp)
                    while len(raid_embed.fields) > 2:
                        raid_embed.remove_field(-1)
                    if moveset:
                        moveset = moveset.split(' / ')
                        for index, m in enumerate(moveset):
                            if m.lower() in self.bot.move_info.keys():
                                moveset[index] = f"{m} {utils.type_to_emoji(self.bot, self.bot.move_info[m.lower()]['type'])}"
                        raid_embed.add_field(name=f"**Moveset:**", value=(' / ').join([x.title() for x in moveset]))
                    now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                    raid_timer = (now + datetime.timedelta(minutes=float(raidexp))).strftime(_('%I:%M %p (%H:%M)'))
                    await ctx.send(f"Meowth! I found this raid at **{train_location}**! This {'egg will hatch' if report_type == 'egg' else 'raid will end'} at {raid_timer}", embed=raid_embed)

    @train.command(name="manager", aliases=["nominate", "elect"])
    @checks.trainchannel()
    async def train_manager(self, ctx, *, user=None):
        """Add new train manager"""
        can_manage = ctx.channel.permissions_for(ctx.author).manage_channels or ctx.author.id in self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'].get(ctx.channel.id, {}).get('managers', [])
        manager_embed = discord.Embed(colour=ctx.guild.me.colour).set_author(name=_('Raid Manager Help')).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/train.png?cache=1')
        manager_embed.add_field(name=f"{ctx.prefix}train start <date and time>", value=f"Sets the train start time. Example: `!train start 6pm`", inline=False)
        manager_embed.add_field(name=f"{ctx.prefix}train end <date and time>", value=f"Sets the train end time. Example: `!train end 7pm`", inline=False)
        manager_embed.add_field(name=f"{ctx.prefix}train manager <user @mention>", value=f"Once you become a train manager, you can promote new train managers using this command. Example: `!train manager @{ctx.guild.me.display_name}`", inline=False)
        manager_embed.add_field(name=f"{ctx.prefix}train route <gym list>", value=f"If you have a planned route, you can set it using this command. Example: `!train route Hershey Park, Liberty Park`", inline=False)
        manager_embed.add_field(name=f"{ctx.prefix}next [gym name]", value=f"Alert the channel that you are going to a new gym. Example: `!next Hershey Park`. If a route is set, train will move to next gym without needing a gym name", inline=False)
        manager_embed.add_field(name=f"{ctx.prefix}starting", value=f"Alert the channel that you are starting at the current location", inline=False)
        if not user:
            member = ctx.author
        else:
            converter = commands.MemberConverter()
            try:
                member = await converter.convert(ctx, user)
            except:
                return
        yes_emoji = self.bot.custom_emoji.get('answer_yes', u'\U00002705')
        no_emoji = self.bot.custom_emoji.get('answer_no', u'\U0000274e')
        reaction = None
        if member.id not in self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'].get(ctx.channel.id, {}).get('managers', []):
            if can_manage:
                self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'][ctx.channel.id]['managers'].append(member.id)
                await ctx.send(f"Meowth! I added **{member.display_name}** as a manager! {member.mention}, check your DMs for instructions!")
                return await member.send(embed=manager_embed, delete_after=3600)
            manager_str = ""
            manager_list = [ctx.guild.get_member(x) for x in self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'].get(ctx.channel.id, {}).get('managers', [])]
            if manager_list:
                manager_str = f"Current managers {', '.join([x.mention for x in manager_list])} can react with {yes_emoji} to instantly add {member.display_name} as a manager for this channel. "
            def check(reaction, user):
                if reaction.message.id == question.id and (reaction.emoji == yes_emoji or reaction.emoji == no_emoji):
                    if reaction.emoji == yes_emoji and user in manager_list and user != ctx.guild.me:
                        return True
                    if reaction.emoji == no_emoji and user != ctx.guild.me:
                        return True
                    return False
            question = await ctx.send(f"Meowth! {ctx.author.mention} nominates {member.mention} as a train leader! {manager_str}All others can object with {no_emoji}. If nobody objects with {no_emoji} in 60 seconds, {member.display_name} will be added as a train manager.")
            await utils.add_reaction(question, yes_emoji)
            await utils.add_reaction(question, no_emoji)
            try:
                timeout = False
                reaction, user = await self.bot.wait_for('reaction_add', check=check, timeout=60)
            except asyncio.TimeoutError:
                timeout = True
            await utils.safe_delete(question)
            if reaction and reaction.emoji == no_emoji:
                return await ctx.send(f"Meowth! The vote for {member.display_name} has failed.", delete_after=10)
            else:
                self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'][ctx.channel.id]['managers'].append(member.id)
                await ctx.send(f"Meowth! I added **{member.display_name}** as a manager! {member.mention}, check your DMs for instructions!")
                return await member.send(embed=manager_embed, delete_after=3600)
        else:
            return await ctx.send(f"Meowth! {member.display_name} is already a manager!", delete_after=10)

    @train.command(name="history")
    @checks.trainchannel()
    async def train_history(self, ctx):
        """View raid train history"""
        if ctx.channel.id not in self.bot.guild_dict[ctx.guild.id]['raidtrain_dict']:
            return
        history_str = ""
        channel_history = self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'][ctx.channel.id]['meetup']['history']
        index = 1
        for item in channel_history:
            if (len(history_str) + len(item)) < 1000:
                history_str += f"**{index})** {item}\n"
            else:
                train_embed.add_field(name="Train Channel History", value=f"This raid train has been to:\n{history_str}")
                history_str = f"**{index})** {item}\n"
            index += 1
        train_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/train.png?cache=1')
        train_embed.add_field(name="Train Channel History", value=f"This raid train has been to:\n{history_str}")
        await ctx.send(embed=train_embed)

    @train.command(name="route", aliases=['path'])
    @checks.trainchannel()
    async def train_route(self, ctx, *, path=''):
        """Set raid train route"""
        if ctx.channel.id not in self.bot.guild_dict[ctx.guild.id]['raidtrain_dict']:
            return
        can_manage = ctx.channel.permissions_for(ctx.author).manage_channels or ctx.author.id in self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'].get(ctx.channel.id, {}).get('managers', [])
        train_path = self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'][ctx.channel.id]['meetup'].setdefault('route', [])
        if path and can_manage:
            gym_matching_cog = self.bot.cogs.get('GymMatching')
            path_list = []
            path_split = path.split(',')
            path_split = [x.strip() for x in path_split]
            for gym in path_split:
                if gym_matching_cog:
                    gym_info, gym, gym_url = await gym_matching_cog.get_poi_info(ctx, gym, "raid")
                if not gym:
                    return await utils.safe_delete(ctx.message)
                path_list.append(gym)
            self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'][ctx.channel.id]['meetup']['route'] = path_list
            return await ctx.send(f"Meowth! The train route has been set to **{(', ').join(path_list)}**")
        elif train_path:
            path_str = ""
            index = 1
            for item in train_path:
                path_str += f"**{index})** {item}\n"
                index += 1
            train_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/train.png?cache=1')
            train_embed.add_field(name="Planned Train Route", value=f"This raid train is currently planned to go to:\n{path_str}")
            await ctx.send(embed=train_embed)
        else:
            return await ctx.send(f"Meowth! No train route has been set! Have a manager set one with **{ctx.prefix}train path**", delete_after=30)

    @train.command(aliases=['expire', 'delete'], name='reset')
    @checks.allowtrainreport()
    @checks.is_mod()
    async def reset_trains(self, ctx, *, channel:discord.TextChannel=None):
        """Reset train channels"""
        await self.raid_reset(ctx, channel, type='train')

    """
    Raid Channel Management
    """

    async def print_raid_timer(self, channel):
        report_dict = await utils.get_report_dict(self.bot, channel)
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
        end = now + datetime.timedelta(seconds=self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['exp'] - time.time())
        timerstr = ' '
        if self.bot.guild_dict[channel.guild.id][report_dict][channel.id].get('meetup', {}):
            end = self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['meetup']['end']
            start = self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['meetup']['start']
            if self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['type'] == 'egg':
                if start:
                    timerstr += _("This event will start at {expiry_time}").format(expiry_time=start.strftime(_('%B %d at %I:%M %p (%H:%M)')))
                else:
                    timerstr += f"Nobody has told me a start time! Set it with **!{'train' if report_dict == 'raidtrain_dict' else 'meetup'} start**"
                if end:
                    timerstr += _(" | This event will end at {expiry_time}").format(expiry_time=end.strftime(_('%B %d at %I:%M %p (%H:%M)')))
            if self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['type'] == 'exraid':
                if end:
                    timerstr += _("This event will end at {expiry_time}").format(expiry_time=end.strftime(_('%B %d at %I:%M %p (%H:%M)')))
                else:
                    timerstr += f"Nobody has told me a end time! Set it with **!{'train' if report_dict == 'raidtrain_dict' else 'meetup'} end**"
            return timerstr
        if self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['type'] == 'egg':
            raidtype = _('egg')
            raidaction = _('hatch')
        else:
            raidtype = _('raid')
            raidaction = _('end')
        if (not self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['active']):
            timerstr += _("This {raidtype}'s timer has already expired as of {expiry_time}!").format(raidtype=raidtype, expiry_time=end.strftime(_('%I:%M %p (%H:%M)')))
        elif (self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['egg_level'] == 'EX') or (self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['type'] == 'exraid'):
            if self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['manual_timer']:
                timerstr += _('This {raidtype} will {raidaction} on {expiry}!').format(raidtype=raidtype, raidaction=raidaction, expiry=end.strftime(_('%B %d at %I:%M %p (%H:%M)')))
            else:
                timerstr += _("No one told me when the {raidtype} will {raidaction}, so I'm assuming it will {raidaction} on {expiry}!").format(raidtype=raidtype, raidaction=raidaction, expiry=end.strftime(_('%B %d at %I:%M %p (%H:%M)')))
        elif self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['manual_timer']:
            timerstr += _('This {raidtype} will {raidaction} at {expiry_time}!').format(raidtype=raidtype, raidaction=raidaction, expiry_time=end.strftime(_('%I:%M %p (%H:%M)')))
        else:
            timerstr += _("No one told me when the {raidtype} will {raidaction}, so I'm assuming it will {raidaction} at {expiry_time}!").format(raidtype=raidtype, raidaction=raidaction, expiry_time=end.strftime(_('%I:%M %p (%H:%M)')))
        return timerstr

    @commands.command(aliases=['timer'])
    @checks.raidchannel()
    async def timerset(self, ctx, *, timer=None):
        """Set the remaining duration on a raid.

        Usage: !timerset <minutes>
        Works only in raid channels, can be set or overridden by anyone.
        Meowth displays the end time in HH:MM local time."""
        message = ctx.message
        channel = message.channel
        guild = message.guild
        hourminute = False
        error = False
        report_dict = await utils.get_report_dict(self.bot, channel)
        type = self.bot.guild_dict[guild.id][report_dict][channel.id]['type']
        timerset_embed = discord.Embed(colour=channel.guild.me.colour).set_author(name="Channel Timer")
        timerset_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_date.png?cache=1")
        if ctx.invoked_with == "timer":
            timerstr = await self.print_raid_timer(ctx.channel)
            if checks.check_exraidchannel(ctx) or checks.check_meetupreport(ctx) or checks.check_trainchannel(ctx):
                timerset_embed.description = f"Meowth! {timerstr}\n\nTo change the timer, use **{ctx.prefix}timerset [date and time]**"
            else:
                timerset_embed.description = f"Meowth! {timerstr}\n\nTo change the timer, use **{ctx.prefix}timerset [minutes remaining]**"
            return await ctx.channel.send(embed=timerset_embed)
        if not timer:
            while True:
                async with ctx.typing():
                    if checks.check_exraidchannel(ctx) or checks.check_meetupreport(ctx) or checks.check_trainchannel(ctx):
                        timerset_embed.description = f"Meowth! I'll help you set the timer for the current channel. Reply with the **date and time** that the {type} {'hatches' if type == 'egg' else 'ends'}."
                    else:
                        timerset_embed.description = f"Meowth! I'll help you set the timer for the current channel. Reply with the **minutes remaining** before the {type} {'hatches' if type == 'egg' else 'ends'}."
                    time_wait = await channel.send(embed=timerset_embed)
                    def check(reply):
                        if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                            return True
                        else:
                            return False
                    try:
                        time_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        time_msg = None
                    await utils.safe_delete(time_wait)
                    if not time_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(time_msg)
                    if time_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    else:
                        timer = time_msg.clean_content
                    break
            if error:
                timerset_embed.clear_fields()
                timerset_embed.add_field(name=_('**Timerset Cancelled**'), value=_("Meowth! Your report has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
                return await channel.send(embed=timerset_embed, delete_after=10)
        if (not checks.check_exraidchannel(ctx)) and not (checks.check_meetupchannel(ctx)) and (not checks.check_trainchannel(ctx)):
            if type == 'egg':
                raidlevel = self.bot.guild_dict[guild.id][report_dict][channel.id]['egg_level']
                raidtype = _('Raid Egg')
                maxtime = self.bot.raid_info['raid_eggs'][raidlevel]['hatchtime']
                msg = _("Did you mean egg hatch time {0} or time remaining before hatch {1}?").format("🥚", "⏲")
                react_list = ['🥚', '⏲']
            else:
                raidlevel = utils.get_level(self.bot, self.bot.guild_dict[guild.id][report_dict][channel.id]['pkmn_obj'])
                raidtype = _('Raid')
                maxtime = self.bot.raid_info['raid_eggs'][raidlevel]['raidtime']
                msg = _("Did you mean raid end time {0} or time remaining before end {1}?").format("💨", "⏲")
                react_list = ['💨', '⏲']
            if timer.isdigit():
                raidexp = int(timer)
            elif ':' in timer:
                question = await ctx.channel.send(msg)
                try:
                    timeout = False
                    res, reactuser = await utils.ask(self.bot, question, ctx.message.author.id, react_list=react_list)
                except TypeError:
                    timeout = True
                await utils.safe_delete(question)
                if timeout or res.emoji == '⏲':
                    hourminute = True
                elif res.emoji == '🥚' or res.emoji == '💨':
                    now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                    start = dateparser.parse(timer)
                    if now.hour > 12 and start.hour < 12 and "m" not in timer:
                        start = start + datetime.timedelta(hours=12)
                    start = start.replace(day=now.day)
                    timediff = relativedelta(start, now)
                    raidexp = (timediff.hours*60) + timediff.minutes + 1
                    if raidexp < 0:
                        return await channel.send(_('Meowth! Please enter a time in the future.'), delete_after=10)
                else:
                    return await channel.send(_("Meowth! I couldn't understand your time format. Try again like this: **!timerset <minutes>**"), delete_after=10)
            elif ':' in timer:
                hourminute = True
            else:
                return await channel.send(_("Meowth! I couldn't understand your time format. Try again like this: **!timerset <minutes>**"), delete_after=10)
            if hourminute:
                (h, m) = re.sub('[a-zA-Z]', '', timer).split(':', maxsplit=1)
                if h == '':
                    h = '0'
                if m == '':
                    m = '0'
                if h.isdigit() and m.isdigit():
                    raidexp = (60 * int(h)) + int(m)
                else:
                    return await channel.send(_("Meowth! I couldn't understand your time format. Try again like this: **!timerset <minutes>**"), delete_after=10)
            if self._timercheck(raidexp, maxtime):
                await channel.send(_("Meowth...that's too long. Level {raidlevel} {raidtype}s currently last no more than {maxtime} minutes...").format(raidlevel=str(raidlevel), raidtype=raidtype.capitalize(), maxtime=str(maxtime)), delete_after=10)
                return
            await self._timerset(channel, raidexp)
        if checks.check_exraidchannel(ctx) or checks.check_meetupchannel(ctx) or checks.check_trainchannel(ctx):
            if checks.check_eggchannel(ctx) or checks.check_exeggchannel(ctx) or checks.check_meetupchannel(ctx) or checks.check_trainchannel(ctx):
                now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                timer_split = timer.lower().split()
                try:
                    start = dateparser.parse(' '.join(timer_split).lower(), settings={'DATE_ORDER': 'MDY'})
                except:
                    if ('am' in ' '.join(timer_split).lower()) or ('pm' in ' '.join(timer_split).lower()):
                        try:
                            start = datetime.datetime.strptime((' '.join(timer_split) + ' ') + str(now.year), '%m/%d %I:%M %p %Y')
                            if start.month < now.month:
                                start = start.replace(year=now.year + 1)
                        except ValueError:
                            await channel.send(_("Meowth! Your timer wasn't formatted correctly. Change your **!timerset** to match this format: **MM/DD HH:MM AM/PM** (You can also omit AM/PM and use 24-hour time!)"), delete_after=10)
                            return
                    else:
                        try:
                            start = datetime.datetime.strptime((' '.join(timer_split) + ' ') + str(now.year), '%m/%d %H:%M %Y')
                            if start.month < now.month:
                                start = start.replace(year=now.year + 1)
                        except ValueError:
                            await channel.send(_("Meowth! Your timer wasn't formatted correctly. Change your **!timerset** to match this format: **MM/DD HH:MM AM/PM** (You can also omit AM/PM and use 24-hour time!)"), delete_after=10)
                            return
                start = start.replace(second=0, microsecond=0)
                if checks.check_meetupchannel(ctx) or checks.check_trainchannel(ctx):
                    starttime = self.bot.guild_dict[guild.id][report_dict][channel.id]['meetup'].get('start', False)
                    if starttime and start < starttime:
                        await channel.send(_('Meowth! Please enter a time after your start time.'), delete_after=10)
                        return
                diff = start - now
                total = diff.total_seconds() / 60
                if now <= start:
                    await self._timerset(channel, total)
                elif now > start:
                    await channel.send(_('Meowth! Please enter a time in the future.'), delete_after=10)
            else:
                await channel.send(_("Meowth! Timerset isn't supported for EX Raids after they have hatched."), delete_after=10)

    def _timercheck(self, time, maxtime):
        return int(time) > int(maxtime)

    async def _timerset(self, raid_channel, exptime):
        exptime = float(exptime)
        guild = raid_channel.guild
        embed = None
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
        end = now + datetime.timedelta(minutes=exptime)
        report_dict = await utils.get_report_dict(self.bot, raid_channel)
        already_expired = self.bot.guild_dict[guild.id][report_dict][raid_channel.id]['active']
        self.bot.guild_dict[guild.id][report_dict][raid_channel.id]['exp'] = time.time() + (exptime * 60)
        self.bot.guild_dict[guild.id][report_dict][raid_channel.id]['active'] = True
        self.bot.guild_dict[guild.id][report_dict][raid_channel.id]['manual_timer'] = True
        topicstr = ''
        if self.bot.guild_dict[guild.id][report_dict][raid_channel.id].get('meetup', {}):
            self.bot.guild_dict[guild.id][report_dict][raid_channel.id]['meetup']['end'] = end
            topicstr += _('Ends on {end}').format(end=end.strftime(_('%B %d at %I:%M %p (%H:%M)')))
            endtime = end.strftime(_('%B %d at %I:%M %p (%H:%M)'))
            field_name = "**Event Ends:**"
        elif self.bot.guild_dict[guild.id][report_dict][raid_channel.id]['type'] == 'egg':
            egg_level = self.bot.guild_dict[guild.id][report_dict][raid_channel.id]['egg_level']
            hatch = end
            end = hatch + datetime.timedelta(minutes=self.bot.raid_info['raid_eggs'][egg_level]['raidtime'])
            topicstr += _('Hatches on {expiry}').format(expiry=hatch.strftime(_('%B %d at %I:%M %p (%H:%M) | ')))
            topicstr += _('Ends on {end}').format(end=end.strftime(_('%B %d at %I:%M %p (%H:%M)')))
            endtime = hatch.strftime(_('%B %d at %I:%M %p (%H:%M)'))
            field_name = "**Hatches:**"
        else:
            topicstr += _('Ends on {end}').format(end=end.strftime(_('%B %d at %I:%M %p (%H:%M)')))
            endtime = end.strftime(_('%B %d at %I:%M %p (%H:%M)'))
            field_name = "**Expires:**"
        timerstr = await self.print_raid_timer(raid_channel)
        timerset_embed = discord.Embed(colour=raid_channel.guild.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_date.png?cache=1")
        if self.bot.guild_dict[guild.id][report_dict][raid_channel.id].get('starttime') and now < self.bot.guild_dict[guild.id][report_dict][raid_channel.id].get('starttime') and not self.bot.guild_dict[guild.id][report_dict][raid_channel.id].get('meetup', {}):
            timerset_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_timer.png?cache=1")
            timerset_embed.add_field(name=f"**Channel Timer**", value=f"Meowth! The current start time is: **{self.bot.guild_dict[guild.id][report_dict][raid_channel.id].get('starttime').strftime(_('%I:%M %p (%H:%M)'))}**\n\n{timerstr}")
        else:
            timerset_embed.add_field(name=f"**Channel Timer**", value=f"{timerstr}")
        if self.bot.guild_dict[guild.id][report_dict][raid_channel.id].get('timerset_msg'):
            try:
                timerset_msg = await raid_channel.fetch_message(self.bot.guild_dict[guild.id][report_dict][raid_channel.id]['timerset_msg'])
                await timerset_msg.edit(content=None, embed=timerset_embed)
            except:
                pass
            if not already_expired:
                timerset_embed.add_field(name=f"**Channel Reactivated**", value=f"The channel was reactivated.", inline=False)
            timerset_msg = await raid_channel.send(embed=timerset_embed, delete_after=60)
        else:
            timerset_msg = await raid_channel.send(embed=timerset_embed)
            self.bot.guild_dict[guild.id][report_dict][raid_channel.id]['timerset_msg'] = timerset_msg.id
        raid_channel_name = await self.edit_channel_name(raid_channel)
        await raid_channel.edit(name=raid_channel_name, topic=topicstr)
        report_channel = self.bot.get_channel(self.bot.guild_dict[guild.id][report_dict][raid_channel.id]['report_channel'])
        raid_report = self.bot.guild_dict[guild.id][report_dict][raid_channel.id]['raid_report']
        report_message = self.bot.guild_dict[guild.id][report_dict][raid_channel.id]['report_message']
        try:
            raidmsg = await raid_channel.fetch_message(self.bot.guild_dict[guild.id][report_dict][raid_channel.id]['raid_message'])
            embed = raidmsg.embeds[0]
            embed.set_thumbnail(url=f"{embed.thumbnail.url.split('&report_message=')[0]}&report_message={report_message}&raid_report={raid_report}")
            index = 0
            for field in embed.fields:
                if _("expires") in field.name.lower() or _("hatches") in field.name.lower() or _("ends:**") in field.name.lower():
                    embed.set_field_at(index, name=field_name, value=endtime, inline=field.inline)
                    break
                else:
                    index += 1
            await raidmsg.edit(content=raidmsg.content, embed=embed)
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, IndexError, AttributeError):
            pass
        try:
            reportmsg = await report_channel.fetch_message(self.bot.guild_dict[guild.id][report_dict][raid_channel.id]['raid_report'])
            await reportmsg.edit(content=reportmsg.content, embed=embed)
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, AttributeError):
            pass
        raid_channel = self.bot.get_channel(raid_channel.id)
        self.bot.loop.create_task(self.expiry_check(raid_channel))

    @commands.command()
    @checks.raidchannel()
    async def starttime(self, ctx, *, start_time=""):
        """Set a time for a group to start a raid

        Usage: !starttime [HH:MM AM/PM or tag]
        (You can also omit AM/PM and use 24-hour time!)
        Works only in raid channels. Sends a message and sets a group start time that
        can be seen using !starttime (without a time). One start time is allowed at
        a time and is visibile in !list output. Cleared with !starting."""
        message = ctx.message
        guild = message.guild
        channel = message.channel
        author = message.author
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
        report_dict = await utils.get_report_dict(self.bot, ctx.channel)
        rc_d = self.bot.guild_dict[guild.id][report_dict][channel.id]
        already_set = rc_d.get('starttime', None)
        meetup = rc_d.get('meetup', {})
        start_split = start_time.lower().split()
        trainer_list = []
        tags = True if "tags" in start_split or "tag" in start_split else False
        timeset = None
        start = None
        starttime_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_timer.png?cache=1")
        if tags:
            start_time = start_time.replace("tags", "").replace("tag", "")
            start_split = start_time.lower().split()
        if not start_time:
            if already_set and already_set < now:
                rc_d['starttime'] = None
                already_set = None
            if already_set:
                if tags:
                    for trainer in rc_d['trainer_dict']:
                        user = ctx.guild.get_member(trainer)
                        if (rc_d['trainer_dict'][trainer]['status']['maybe'] or rc_d['trainer_dict'][trainer]['status']['coming']) and user:
                            trainer_list.append(user.mention)
                starttime_embed.add_field(name=f"**Channel Start Time**", value=f"{', '.join(trainer_list)}\n\nMeowth! The current start time is: **{already_set.strftime(_('%I:%M %p (%H:%M)'))}**")
                return await channel.send(embed=starttime_embed, delete_after=60)
            else:
                starttime_embed.add_field(name=f"**Channel Start Time**", value=f"Meowth! No start time has been set, set one with **!starttime HH:MM AM/PM**! (You can also omit AM/PM and use 24-hour time!")
                return await channel.send(embed=starttime_embed, delete_after=10)
        if meetup:
            try:
                start = dateparser.parse(' '.join(start_split).lower(), settings={'DATE_ORDER': 'MDY'})
                endtime = self.bot.guild_dict[guild.id][report_dict][channel.id]['meetup'].get('end', False)
                if start < now:
                    starttime_embed.add_field(name=f"**Channel Start Time**", value=f"Meowth! Please enter a time in the future.")
                    return await channel.send(embed=starttime_embed, delete_after=10)
                if endtime and start > endtime:
                    starttime_embed.add_field(name=f"**Channel Start Time**", value=f"Meowth! Please enter a time before your end time.")
                    return await channel.send(embed=starttime_embed, delete_after=10)
                timeset = True
                rc_d['meetup']['start'] = start
            except:
                pass
        if not timeset:
            if rc_d['type'] == 'egg':
                egg_level = rc_d['egg_level']
                mintime = (rc_d['exp'] - time.time()) / 60
                maxtime = mintime + self.bot.raid_info['raid_eggs'][egg_level]['raidtime']
            elif (rc_d['type'] == 'raid') or (rc_d['type'] == 'exraid'):
                egg_level = utils.get_level(self.bot, rc_d['pkmn_obj'])
                mintime = 0
                maxtime = (rc_d['exp'] - time.time()) / 60
            if len(start_split) > 0:
                start = dateparser.parse(' '.join(start_split).lower(), settings={'DATE_ORDER': 'MDY'})
                if egg_level == 'EX':
                    hatch = datetime.datetime.utcfromtimestamp(rc_d['exp']) + datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                    start = start.replace(year=hatch.year, month=hatch.month, day=hatch.day)
                if not start:
                    starttime_embed.add_field(name=f"**Channel Start Time**", value=f"Meowth! I didn\'t quite get that, try again.")
                    return await channel.send(embed=starttime_embed, delete_after=10)
                diff = start - now
                total = diff.total_seconds() / 60
                if total > maxtime and egg_level != 'EX':
                    starttime_embed.add_field(name=f"**Channel Start Time**", value=f"Meowth! The raid will be over before that....")
                    return await channel.send(embed=starttime_embed, delete_after=10)
                if now > start and egg_level != 'EX':
                    starttime_embed.add_field(name=f"**Channel Start Time**", value=f"Meowth! Please enter a time in the future.")
                    return await channel.send(embed=starttime_embed, delete_after=10)
                if int(total) < int(mintime) and egg_level != 'EX':
                    starttime_embed.add_field(name=f"**Channel Start Time**", value=f"Meowth! The egg will not hatch by then!")
                    return await channel.send(embed=starttime_embed, delete_after=10)
                if already_set:
                    starttime_embed.add_field(name=f"**Channel Start Time**", value=f"Meowth! There is already a start time of **{already_set.strftime(_('%I:%M %p (%H:%M)'))}** set! Do you want to change it?")
                    rusure = await channel.send(embed=starttime_embed)
                    try:
                        timeout = False
                        res, reactuser = await utils.ask(self.bot, rusure, author.id)
                    except TypeError:
                        timeout = True
                    if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', u'\U0000274e'):
                        await utils.safe_delete(rusure)
                        confirmation = await channel.send(_('Start time change cancelled.'), delete_after=10)
                        return
                    elif res.emoji == self.bot.custom_emoji.get('answer_yes', u'\U00002705'):
                        await utils.safe_delete(rusure)
                        if now <= start:
                            timeset = True
                    else:
                        return
        if (start and now <= start) or timeset:
            meetup = self.bot.guild_dict[guild.id][report_dict][channel.id].get('meetup')
            starttime_embed.clear_fields()
            rc_d['starttime'] = start
            nextgroup = start.strftime(_('%I:%M %p (%H:%M)'))
            if rc_d.get('meetup', {}):
                nextgroup = start.strftime(_('%B %d at %I:%M %p (%H:%M)'))
                end = rc_d['meetup'].get('end', False)
                if end:
                    topicstr = _("Starts on {expiry} | Ends on {end}").format(expiry=start.strftime(_('%B %d at %I:%M %p (%H:%M)')), end=end.strftime(_('%B %d at %I:%M %p (%H:%M)')))
                else:
                    topicstr = _("Starts on {expiry}").format(expiry=start.strftime(_('%B %d at %I:%M %p (%H:%M)')))
                await channel.edit(topic=topicstr)
            timerstr = await self.print_raid_timer(ctx.channel)
            if meetup:
                starttime_embed.add_field(name=f"**Channel Timer - Start Time**", value=f"{timerstr}").set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_date.png?cache=1")
            else:
                starttime_embed.add_field(name=f"**Channel Timer - Start Time**", value=f"Meowth! The current start time has been set to: **{nextgroup}**\n\n{timerstr}")
            await channel.send(embed=starttime_embed, delete_after=60)
            report_channel = self.bot.get_channel(rc_d['report_channel'])
            raidmsg = await channel.fetch_message(rc_d['raid_message'])
            reportmsg = await report_channel.fetch_message(rc_d['raid_report'])
            userreport = rc_d['report_message']
            embed = raidmsg.embeds[0]
            embed.set_thumbnail(url=f"{embed.thumbnail.url.split('&report_message=')[0]}&report_message={userreport}&raid_report={reportmsg.id}")
            index = 0
            for field in embed.fields:
                if _("**Next Group:**") in field.name or _("Starts:**") in field.name:
                    embed.set_field_at(index, name=field.name, value=nextgroup, inline=field.inline)
                    break
                else:
                    index += 1
            try:
                await raidmsg.edit(content=raidmsg.content, embed=embed)
            except discord.errors.NotFound:
                pass
            try:
                await reportmsg.edit(content=reportmsg.content, embed=embed)
            except discord.errors.NotFound:
                pass
            try:
                timerset_msg = await ctx.channel.fetch_message(self.bot.guild_dict[guild.id][report_dict][ctx.channel.id]['timerset_msg'])
                await timerset_msg.edit(content=None, embed=starttime_embed)
            except:
                pass
            return

    @commands.command()
    @checks.raidchannel()
    async def moveset(self, ctx, *, moves):
        """Set boss moveset

        Usage: !moveset <move 1>, [move 2]"""
        if not checks.check_hatchedraid(ctx):
            return await ctx.send(f"Meowth! Please wait until the egg has hatched before setting moveset!", delete_after=10)
        await self.set_moveset(ctx, ctx.channel, moves)

    async def set_moveset(self, ctx, channel, moves):
        moveset = 0
        newembed = False
        moveset_str = ""
        report_dict = await utils.get_report_dict(ctx.bot, channel)
        try:
            ctrs_message = await channel.fetch_message(self.bot.guild_dict[ctx.channel.guild.id][report_dict][channel.id]['ctrsmessage'])
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, KeyError):
            ctrs_message = None
        except AttributeError:
            return
        ctrs_dict = self.bot.guild_dict[channel.guild.id][report_dict][channel.id].get('ctrs_dict', {})
        entered_raid = self.bot.guild_dict[channel.guild.id][report_dict][channel.id].get('pkmn_obj', "")
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, entered_raid)
        weather =  self.bot.guild_dict[channel.guild.id][report_dict][channel.id].get('weather', None)
        if not ctrs_dict:
            ctrs_dict = await self._get_generic_counters(ctx.channel, entered_raid, weather)
            self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['ctrs_dict'] = ctrs_dict
        if not moves or not ctrs_dict or not pokemon.quick_moves or not pokemon.charge_moves:
            return
        moves = re.split('\\||/|,', moves)
        moves = [x.strip().title() for x in moves]
        moves = [x for x in moves if x.lower() in pokemon.quick_moves+pokemon.charge_moves]
        charge_move = ""
        quick_move = ""
        for m in moves:
            if m in [x.title() for x in pokemon.charge_moves]:
                charge_move = m
            elif m in [x.title() for x in pokemon.quick_moves]:
                quick_move = m
        moves = []
        if quick_move:
            moves.append(quick_move)
        if charge_move:
            moves.append(charge_move)
        if len(moves) > 2 or len(moves) == 0:
            return
        elif len(moves) == 2:
            for i in ctrs_dict:
                if ctrs_dict[i]['moveset'] == (' | ').join(moves):
                    newembed = ctrs_dict[i]['embed']
                    moveset = i
                    break
            if ctrs_message and newembed:
                await ctrs_message.edit(embed=newembed)
            self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['moveset'] = moveset
        self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['moves'] = (' / ').join(moves)
        for index, m in enumerate(moves):
            if m.lower() in self.bot.move_info.keys():
                moves[index] = f"{m} {utils.type_to_emoji(self.bot, self.bot.move_info[m.lower()]['type'])}"
        moveset_embed = discord.Embed(colour=channel.guild.me.colour).set_thumbnail(url=pokemon.img_url)
        moveset_embed.add_field(name=f"**Boss Moveset**", value=f"This {str(pokemon)}'s {'moves are' if len(moves)>1 else 'move is'}:\n**{(' / ').join([x.title() for x in moves])}**")
        await channel.send(embed=moveset_embed, delete_after=600)
        try:
            raid_msg = await channel.fetch_message(self.bot.guild_dict[ctx.guild.id][report_dict][channel.id]['raid_message'])
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
            return
        raid_embed = raid_msg.embeds[0]
        for index, field in enumerate(raid_embed.fields):
            if "list" in field.name.lower() or "moveset" in field.name.lower():
                raid_embed.remove_field(index)
        raid_embed.add_field(name="**Moveset**:", value=(' / ').join([x.title() for x in moves]), inline=True)
        await raid_msg.edit(embed=raid_embed)
        await self._edit_party(channel)

    @commands.group(case_insensitive=True)
    @checks.rsvpchannel()
    async def location(self, ctx):
        """Get raid location.

        Usage: !location
        Works only in raid channels. Gives the raid location link."""
        if ctx.invoked_subcommand == None:
            message = ctx.message
            guild = message.guild
            channel = message.channel
            report_dict = await utils.get_report_dict(self.bot, channel)
            rc_d = self.bot.guild_dict[guild.id][report_dict]
            meetup = rc_d.get(ctx.channel.id, {}).get('meetup', {})
            raidmsg = await channel.fetch_message(rc_d[channel.id]['raid_message'])
            location = rc_d[channel.id]['address']
            report_channel = self.bot.get_channel(rc_d[channel.id]['report_channel'])
            oldembed = raidmsg.embeds[0]
            locurl = oldembed.url
            newembed = discord.Embed(title=oldembed.title, description=oldembed.description, url=locurl, colour=guild.me.colour)
            for field in oldembed.fields:
                newembed.add_field(name=field.name, value=field.value, inline=field.inline)
            newembed.set_footer(text=oldembed.footer.text, icon_url=oldembed.footer.icon_url)
            newembed.set_thumbnail(url=oldembed.thumbnail.url)
            newembed.set_author(name=oldembed.author.name, icon_url=oldembed.author.icon_url)
            locationmsg = await channel.send(f"Meowth! Here's the current location for the {'meetup' if meetup else 'raid'}! You can modify using **{ctx.prefix}location new**\nDetails: {location}", embed=newembed, delete_after=60)

    @location.command()
    @checks.rsvpchannel()
    async def new(self, ctx, *, content):
        """Change raid location.

        Usage: !location new <new address>
        Works only in raid channels. Changes the google map links."""
        message = ctx.message
        location_split = content.lower().split()
        if len(location_split) < 1:
            await message.channel.send(_("Meowth! We're missing the new location details! Usage: **!location new <new address>**"), delete_after=10)
            return
        else:
            report_dict = await utils.get_report_dict(self.bot, ctx.channel)
            report_channel = self.bot.get_channel(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['report_channel'])
            report_type = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].get('type', None)
            old_location = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].get('address', None)
            report_level = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].get('egg_level', None)
            report_meetup = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].get('meetup', None)
            report_pokemon = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].get('pkmn_obj', None)
            report_message = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].get('report_message', None)
            raid_report = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].get('raid_report', None)
            report_train = True if report_dict == "raidtrain_dict" else False
            raidtype = "meetup" if report_meetup else report_type
            raidtype = "train" if report_train else raidtype
            if not report_channel:
                async for m in ctx.channel.history(limit=500, oldest_first=True):
                    if m.author.id == ctx.guild.me.id:
                        c = _('Coordinate here')
                        if c in m.content:
                            report_channel = m.raw_channel_mentions[0]
                            break
            can_manage = ctx.channel.permissions_for(ctx.author).manage_channels
            report_city = report_channel.name
            raid_details = ' '.join(location_split)
            raid_gmaps_link = utils.create_gmaps_query(self.bot, raid_details, report_channel, type=raidtype)
            gym_matching_cog = self.bot.cogs.get('GymMatching')
            gym_info = ""
            if gym_matching_cog:
                gym_info, raid_details, gym_url = await gym_matching_cog.get_poi_info(ctx, raid_details, "raid")
                if gym_url:
                    raid_gmaps_link = gym_url
            if not raid_details:
                await utils.safe_delete(ctx.message)
                return
            oldraidmsg = await ctx.channel.fetch_message(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['raid_message'])
            try:
                oldreportmsg = await report_channel.fetch_message(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['raid_report'])
            except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                pass
            oldembed = oldraidmsg.embeds[0]
            newembed = discord.Embed(title=oldembed.title, description=gym_info, url=raid_gmaps_link, colour=ctx.guild.me.colour)
            for field in oldembed.fields:
                t = _('team')
                s = _('status')
                r = _('reaction')
                if (t not in field.name.lower()) and (s not in field.name.lower()) and (r not in field.name.lower()):
                    newembed.add_field(name=field.name, value=field.value, inline=field.inline)
            if report_meetup:
                index = 0
                for field in oldembed.fields:
                    if _("Location:**") in field.name:
                        newembed.set_field_at(index, name=field.name, value=raid_details, inline=field.inline)
                        break
                    else:
                        index += 1
            newembed.set_footer(text=oldembed.footer.text, icon_url=oldembed.footer.icon_url)
            newembed.set_thumbnail(url=f"{oldembed.thumbnail.url.split('&report_message=')[0]}&report_message={report_message}&raid_report={raid_report}")
            newembed.set_author(name=oldembed.author.name, icon_url=oldembed.author.icon_url)
            otw_list = []
            rsvp_list = []
            trainer_dict = copy.deepcopy(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['trainer_dict'])
            for trainer in trainer_dict.keys():
                if trainer_dict[trainer]['status']['coming']:
                    user = message.guild.get_member(trainer)
                    if not user:
                        continue
                    otw_list.append(user.mention)
                if trainer_dict[trainer]['status']['maybe'] or trainer_dict[trainer]['status']['coming'] or trainer_dict[trainer]['status']['here']:
                    user = message.guild.get_member(trainer)
                    if not user:
                        continue
                    rsvp_list.append(user.mention)
            location_msg = f"Meowth! Someone has suggested a different location for the {raidtype}!{' Trainers ' if otw_list else ''}{', '.join(otw_list)}{': make sure you are headed to the right place!' if otw_list else ''}"
            if report_dict == "raidtrain_dict":
                location_msg = f"Meowth! The next train location has been selected!{' Trainers ' if rsvp_list else ''}{', '.join(rsvp_list)}{': make sure you are headed to the right place!' if rsvp_list else ''}"
            await ctx.channel.send(content=location_msg, embed=newembed)
            for field in oldembed.fields:
                t = _('team')
                s = _('status')
                r = _('reaction')
                if (t in field.name.lower()) or (s in field.name.lower()) or (r in field.name.lower()):
                    newembed.add_field(name=field.name, value=field.value, inline=field.inline)
            try:
                await oldraidmsg.edit(embed=newembed, content=oldraidmsg.content.replace(old_location, raid_details))
                self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['raid_message'] = oldraidmsg.id
            except:
                pass
            try:
                await oldreportmsg.edit(embed=newembed, content=oldreportmsg.content.replace(old_location, raid_details))
                self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['raid_report'] = oldreportmsg.id
            except:
                pass
            self.bot.guild_dict[message.guild.id][report_dict][ctx.channel.id]['address'] = raid_details
            if can_manage or report_train:
                raid_channel_name = await self.edit_channel_name(ctx.channel)
                if report_meetup:
                    channel_name = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['meetup']['channel_name']
                    question = await ctx.channel.send(f"Would you like to change the channel name to {ctx.channel.name.replace('train-', '').replace('meetup-', '').replace(channel_name, '')}{raidtype.lower()}-{utils.sanitize_channel_name(raid_details).lower()}?")
                    try:
                        timeout = False
                        res, reactuser = await utils.ask(self.bot, question, ctx.author.id)
                    except TypeError:
                        timeout = True
                    if timeout:
                        return
                    if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', u'\U0000274e'):
                        await utils.safe_delete(question)
                        return
                    elif res.emoji == self.bot.custom_emoji.get('answer_yes', u'\U00002705'):
                        self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['meetup']['channel_name'] = utils.sanitize_channel_name(raid_details).lower()
                        raid_channel_name = await self.edit_channel_name(ctx.channel)
                        await utils.safe_delete(question)
                await ctx.channel.edit(name=raid_channel_name)

    @commands.command()
    async def recover(self, ctx):
        """Recover a raid channel if it is no longer responding to commands

        Usage: !recover
        Only necessary after a crash."""
        meetup_cog = self.bot.get_cog('Meetup')
        if checks.check_wantchannel(ctx) or checks.check_citychannel(ctx) or checks.check_raidchannel(ctx) or checks.check_eggchannel(ctx) or checks.check_exraidchannel(ctx) or checks.check_trainchannel(ctx) or checks.check_meetupchannel(ctx):
            await ctx.channel.send(_("Meowth! I can't recover this channel because I know about it already!"), delete_after=10)
            if ctx.channel.id in self.bot.active_channels.keys():
                del self.bot.active_channels[ctx.channel.id]
                self.bot.loop.create_task(self.expiry_check(ctx.channel))
        else:
            channel = ctx.channel
            guild = channel.guild
            name = channel.name
            topic = channel.topic
            for word in list(name.split('-')):
                if word in self.bot.raid_list or word == "level" or word == "meetup" or word == "train" or word.isdigit():
                    break
                name = name.replace(word, '').lstrip('-')
            egg = re.match(r'[1-5]-egg', name)
            meetup = re.match(_('meetup'), name)
            train = re.match(_('train'), name)
            now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
            timerset_msg = None
            weather_msg = None
            ctrs_message = None
            reportchannel = None
            raid_message = None
            report_author = None
            pkmn_obj = None
            weather = None
            trainer_dict = {}
            async for message in channel.history(limit=500, oldest_first=True):
                if message.author.id == guild.me.id or "Meowth" in message.author.display_name:
                    if message.embeds:
                        if f"Coordinate here" in message.content:
                            reportchannel = message.raw_channel_mentions[0]
                            report_author = message.raw_mentions[0]
                            raid_message = message
                        elif message.embeds[0].fields and "channel timer" in message.embeds[0].fields[0].name.lower():
                            timerset_msg = message.id
                        elif message.embeds[0].fields and "channel weather" in message.embeds[0].fields[0].name.lower():
                            weather_msg = message.id
                            weather_search = re.search(r'currently set to (.*)\. This', message.embeds[0].fields[0].value)
                            if weather_search and weather_search.group(1) != "None":
                                weather = weather_search.group(1).lower()
                        elif "best counters" in message.content.lower():
                            ctrs_message = message.id
            try:
                report_message = int(parse.parse_qs(parse.urlparse(raid_message.embeds[0].thumbnail.url).query).get('report_message', [None])[0])
                raid_report = int(parse.parse_qs(parse.urlparse(raid_message.embeds[0].thumbnail.url).query).get('raid_report', [None])[0])
            except:
                report_message = None
                raid_report = None
            if egg:
                raidtype = 'egg'
                report_dict = 'raidchannel_dict'
                chsplit = egg.string.split('-')
                egg_level = chsplit[0]
                del chsplit[0]
                del chsplit[0]
                raid_details = ' '.join(chsplit)
                raid_details = raid_details.strip()
                if (not topic) and raid_message:
                    exp = raid_message.created_at.replace(tzinfo=datetime.timezone.utc).timestamp() + (60 * self.bot.raid_info['raid_eggs'][egg_level]['hatchtime'])
                    manual_timer = False
                else:
                    topicsplit = topic.split('|')
                    localhatch = datetime.datetime.strptime(topicsplit[0][:(- 9)], 'Hatches on %B %d at %I:%M %p')
                    utchatch = localhatch - datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                    exp = utchatch.replace(year=now.year, tzinfo=datetime.timezone.utc).timestamp()
                    manual_timer = True
                pokemon = ''
                if len(self.bot.raid_info['raid_eggs'][egg_level]['pokemon']) == 1:
                    pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, self.bot.raid_info['raid_eggs'][egg_level]['pokemon'][0])
                    pokemon = pokemon.name.lower()
            elif name.split('-')[0] in self.bot.raid_list:
                raidtype = 'raid'
                report_dict = 'raidchannel_dict'
                egg_level = '0'
                chsplit = name.split('-')
                pokemon = chsplit[0]
                del chsplit[0]
                raid_details = ' '.join(chsplit)
                raid_details = raid_details.strip()
                if (not topic) and raid_message:
                    exp = raid_message.created_at.replace(tzinfo=datetime.timezone.utc).timestamp() + (60 * self.bot.raid_info['raid_eggs'][utils.get_level(self.bot, pokemon)]['raidtime'])
                    manual_timer = False
                else:
                    localend = datetime.datetime.strptime(topic[:(- 8)], _('Ends on %B %d at %I:%M %p'))
                    utcend = localend - datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                    exp = utcend.replace(year=now.year, tzinfo=datetime.timezone.utc).timestamp()
                    manual_timer = True
                pkmn = await pkmn_class.Pokemon.async_get_pokemon(self.bot, pokemon)
                if pkmn:
                    pkmn_obj = str(pokemon)
            elif name.split('-')[0] == 'ex':
                raidtype = 'egg'
                report_dict = 'exraidchannel_dict'
                egg_level = 'EX'
                chsplit = name.split('-')
                del chsplit[0]
                del chsplit[0]
                del chsplit[0]
                raid_details = ' '.join(chsplit)
                raid_details = raid_details.strip()
                if (not topic) and raid_message:
                    exp = raid_message.created_at.replace(tzinfo=datetime.timezone.utc).timestamp() + (((60 * 60) * 24) * 14)
                    manual_timer = False
                else:
                    topicsplit = topic.split('|')
                    localhatch = datetime.datetime.strptime(topicsplit[0][:(- 9)], 'Hatches on %B %d at %I:%M %p')
                    utchatch = localhatch - datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                    exp = utchatch.replace(year=now.year, tzinfo=datetime.timezone.utc).timestamp()
                    manual_timer = True
                pokemon = ''
                if len(self.bot.raid_info['raid_eggs']['EX']['pokemon']) == 1:
                    pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, self.bot.raid_info['raid_eggs']['EX']['pokemon'][0])
                    pokemon = pokemon.name.lower()
            elif train:
                raidtype = 'egg'
                report_dict = 'raidtrain_dict'
                egg_level = 'EX'
                chsplit = name.split('-')
                del chsplit[0]
                raid_details = ' '.join(chsplit)
                raid_details = raid_details.strip()
                await channel.edit(topic="")
                exp = raid_message.created_at.replace(tzinfo=datetime.timezone.utc).timestamp() + (((60 * 60) * 24) * 14)
                manual_timer = False
                pokemon = ''
            elif meetup:
                raidtype = 'egg'
                report_dict = 'meetup_dict'
                egg_level = 'EX'
                chsplit = name.split('-')
                del chsplit[0]
                raid_details = ' '.join(chsplit)
                raid_details = raid_details.strip()
                await channel.edit(topic="")
                exp = raid_message.created_at.replace(tzinfo=datetime.timezone.utc).timestamp() + (((60 * 60) * 24) * 14)
                manual_timer = False
                pokemon = ''
            else:
                await channel.send(_("Meowth! I couldn't recognize this as a raid channel!"), delete_after=10)
                return
            async for message in channel.history(limit=500):
                if message.author.id == guild.me.id or "Meowth" in message.author.display_name:
                    if (_('is interested') in message.content) or (_('on the way') in message.content) or (_('at the raid') in message.content) or (_('at the event') in message.content) or (_('no longer') in message.content) or (_('left the raid') in message.content):
                        if message.raw_mentions:
                            if message.raw_mentions[0] not in trainer_dict:
                                trainerid = message.raw_mentions[0]
                                user = ctx.guild.get_member(trainerid)
                                if not user:
                                    continue
                                status = {'maybe':0, 'coming':0, 'here':0, 'lobby':0}
                                trainerstatus = None
                                if _('is interested') in message.content:
                                    trainerstatus = 'maybe'
                                elif _('on the way') in message.content:
                                    trainerstatus = 'coming'
                                elif _('at the') in message.content:
                                    trainerstatus = 'here'
                                elif (_('no longer') in message.content) or (_('left the raid') in message.content):
                                    trainerstatus = None
                                if _('trainers') in message.content:
                                    messagesplit = message.content.split()
                                    count = re.search(r'total of \*\*(.*)\*\*', message.content)
                                    count = int(count.group(1))
                                    party = {'mystic':0, 'valor':0, 'instinct':0, 'unknown':0}
                                    for index, item in enumerate(messagesplit):
                                        if ":mystic:" in item:
                                            party['mystic'] = int(messagesplit[index+1])
                                        elif ":valor:" in item:
                                            party['valor'] = int(messagesplit[index+1])
                                        elif ":instinct:" in item:
                                            party['instinct'] = int(messagesplit[index+1])
                                        elif ":grey_question:" in item:
                                            party['unknown'] = int(messagesplit[index+1])
                                elif trainerstatus:
                                    count = 1
                                    for role in user.roles:
                                        if role.id == self.bot.guild_dict[guild.id]['configure_dict'].get('team', {}).get('team_roles', {}).get('mystic', 0):
                                            party = {'mystic':1, 'valor':0, 'instinct':0, 'unknown':0}
                                            break
                                        elif role.id == self.bot.guild_dict[guild.id]['configure_dict'].get('team', {}).get('team_roles', {}).get('valor', 0):
                                            party = {'mystic':0, 'valor':1, 'instinct':0, 'unknown':0}
                                            break
                                        elif role.id == self.bot.guild_dict[guild.id]['configure_dict'].get('team', {}).get('team_roles', {}).get('instinct', 0):
                                            party = {'mystic':0, 'valor':0, 'instinct':1, 'unknown':0}
                                            break
                                        else:
                                            party = {'mystic':0, 'valor':0, 'instinct':0, 'unknown':1}
                                else:
                                    count = 0
                                    party = {'mystic':0, 'valor':0, 'instinct':0, 'unknown':0}
                                if trainerstatus:
                                    status[trainerstatus] = count
                                trainer_dict[trainerid] = {
                                    'status': status,
                                    'count': count,
                                    'party': party
                                }
                            else:
                                continue
                        else:
                            continue
            if not report_dict:
                question = await ctx.channel.send(f"{ctx.author.mention} Is this a raid \u2694, an exraid \U0001F39F, a meetup \U0001F46A, or a train \U0001F682 channel?")
                try:
                    timeout = False
                    res, reactuser = await utils.ask(self.bot, question, ctx.author.id, react_list=['\u2694', '\U0001F39F', '\U0001F46A', u'\U0001F539'])
                except TypeError:
                    timeout = True
                if timeout:
                    report_dict = 'raidchannel_dict'
                if res.emoji == '\u2694':
                    report_dict = 'raidchannel_dict'
                elif res.emoji == '\U0001F682':
                    report_dict = 'raidtrain_dict'
                elif res.emoji == '\U0001F46A':
                    report_dict = 'meetup_dict'
                elif res.emoji == '\U0001F39F':
                    report_dict = 'exraidchannel_dict'
                await utils.safe_delete(question)
            self.bot.guild_dict[channel.guild.id][report_dict][channel.id] = {
                'report_channel':reportchannel,
                'report_guild':channel.guild.id,
                'report_author':report_author,
                'trainer_dict': trainer_dict,
                'report_time':time.time(),
                'exp': exp,
                'manual_timer': manual_timer,
                'active': True,
                'raid_message':raid_message.id,
                'raid_report':raid_report,
                'raid_embed': raid_message.embeds[0],
                'report_message':report_message,
                'address': raid_details,
                'type': raidtype,
                'pokemon': pokemon,
                'egg_level':egg_level,
                'pkmn_obj': pkmn_obj,
                'timerset_msg': timerset_msg,
                'weather_msg':weather_msg,
                'coordinates':'',
                'weather':weather
            }
            raid_channel_name = await self.edit_channel_name(ctx.channel)
            await ctx.channel.edit(name=raid_channel_name)
            recovermsg = _("Meowth! This channel has been recovered! However, there may be some inaccuracies in what I remembered! Here's what I have:")
            if "channel" in report_dict and pkmn_obj:
                self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['ctrsmessage'] = ctrs_message
                ctrs_dict = await self._get_generic_counters(ctx.channel, pkmn_obj, weather.lower())
                self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['ctrs_dict'] = ctrs_dict
                self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['moveset'] = 0
            if train:
                self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'][ctx.channel.id]['managers'] = [ctx.author.id]
                for member in ctx.guild.members:
                    if ctx.channel.permissions_for(member).manage_channels:
                        self.bot.guild_dict[ctx.guild.id]['raidtrain_dict'][ctx.channel.id]['managers'].append(member.id)
                recovermsg += _(" You will have to set the train managers again.")
            if meetup or train:
                self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['meetup'] = {'start':False, 'end':False}
                self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['meetup']['channel_name'] = name.replace('train-', '').replace('meetup-', '')
                recovermsg += _(" You will have to set the event times again.")
            await self._edit_party(channel, message.author)
            bulletpoint = self.bot.custom_emoji.get('bullet', u'\U0001F539')
            list_cog = self.bot.get_cog('Listing')
            if not list_cog:
                self.bot.loop.create_task(self.expiry_check(channel))
                return await channel.send(recovermsg)
            recovermsg += ('\n' + bulletpoint) + (await list_cog._interest(ctx))
            recovermsg += ('\n' + bulletpoint) + (await list_cog._otw(ctx))
            recovermsg += ('\n' + bulletpoint) + (await list_cog._waiting(ctx))
            if (not manual_timer) and not meetup and not train:
                if raidtype == 'egg':
                    action = _('hatch')
                    type = _('egg')
                elif raidtype == 'raid':
                    action = _('end')
                    type = _('raid')
                recovermsg += _("\nI'm not sure when this {raidtype} will {action}, so please use **!timerset** if you can!").format(raidtype=type, action=action)
            else:
                recovermsg += ('\n' + bulletpoint) + (await self.print_raid_timer(channel))
            await self._edit_party(channel, ctx.message.author)
            await channel.send(recovermsg)
            self.bot.loop.create_task(self.expiry_check(channel))

    @commands.command()
    @checks.activeraidchannel()
    async def duplicate(self, ctx):
        """A command to report a raid channel as a duplicate.

        Usage: !duplicate
        Works only in raid channels. When three users report a channel as a duplicate,
        Meowth deactivates the channel and marks it for deletion."""
        channel = ctx.channel
        author = ctx.author
        guild = ctx.guild
        report_dict = await utils.get_report_dict(ctx.bot, ctx.channel)
        rc_d = self.bot.guild_dict[guild.id][report_dict][channel.id]
        report_author = guild.get_member(rc_d['report_author'])
        t_dict = rc_d['trainer_dict']
        can_manage = channel.permissions_for(author).manage_channels
        raidtype = _("event") if self.bot.guild_dict[guild.id][report_dict][channel.id].get('meetup', False) else _("raid")
        if can_manage:
            dupecount = 2
            rc_d['duplicate'] = dupecount
        else:
            if author.id in t_dict:
                try:
                    if t_dict[author.id]['dupereporter']:
                        dupeauthmsg = await channel.send(_("Meowth! You've already made a duplicate report for this {raidtype}!").format(raidtype=raidtype), delete_after=10)
                        return
                    else:
                        t_dict[author.id]['dupereporter'] = True
                except KeyError:
                    t_dict[author.id]['dupereporter'] = True
            else:
                t_dict[author.id] = {
                    'status': {'maybe':0, 'coming':0, 'here':0, 'lobby':0},
                    'dupereporter': True,
                }
            try:
                dupecount = rc_d['duplicate']
            except KeyError:
                dupecount = 0
                rc_d['duplicate'] = dupecount
        dupecount += 1
        rc_d['duplicate'] = dupecount
        if dupecount >= 3:
            rusure = await channel.send(_('Meowth! Are you sure you wish to remove this {raidtype}?').format(raidtype=raidtype))
            try:
                timeout = False
                res, reactuser = await utils.ask(self.bot, rusure, author.id)
            except TypeError:
                timeout = True
            if not timeout:
                if res.emoji == self.bot.custom_emoji.get('answer_no', u'\U0000274e'):
                    await utils.safe_delete(rusure)
                    confirmation = await channel.send(_('Duplicate Report cancelled.'), delete_after=10)
                    logger.info((('Duplicate Report - Cancelled - ' + channel.name) + ' - Report by ') + author.name)
                    dupecount = 2
                    self.bot.guild_dict[guild.id][report_dict][channel.id]['duplicate'] = dupecount
                    return
                elif res.emoji == self.bot.custom_emoji.get('answer_yes', u'\U00002705'):
                    await utils.safe_delete(rusure)
                    await channel.send(_('Duplicate Confirmed'), delete_after=10)
                    logger.info((('Duplicate Report - Channel Expired - ' + channel.name) + ' - Last Report by ') + author.name)
                    raidmsg = await channel.fetch_message(rc_d['raid_message'])
                    reporter = raidmsg.mentions[0]
                    if 'egg' in raidmsg.content and not reporter.bot:
                        egg_reports = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(reporter.id, {}).setdefault('egg_reports', 0)
                        self.bot.guild_dict[guild.id]['trainers'][reporter.id]['egg_reports'] = egg_reports - 1
                    elif 'EX' in raidmsg.content and not reporter.bot:
                        ex_reports = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(reporter.id, {}).setdefault('ex_reports', 0)
                        self.bot.guild_dict[guild.id]['trainers'][reporter.id]['ex_reports'] = ex_reports - 1
                    else:
                        raid_reports = self.bot.guild_dict[guild.id].setdefault('trainers', {}).setdefault(reporter.id, {}).setdefault('raid_reports', 0)
                        self.bot.guild_dict[guild.id]['trainers'][reporter.id]['raid_reports'] = raid_reports - 1
                    if report_author.bot:
                        askdupe = await channel.send(_('Hey {reporter}, this is a bot channel that has some additional features. If you send me a channel mention (#channel) of the other channel I can move those features to it.').format(reporter=ctx.author.mention))
                        while True:
                            def checkmsg(msg):
                                if msg.author is not guild.me and msg.channel.id == channel.id:
                                    return True
                                else:
                                    return False
                            try:
                                getdupe = await self.bot.wait_for('message', check=checkmsg, timeout=240)
                            except asyncio.TimeoutError:
                                await channel.send("I didn't get a message so I'll expire the channel.", delete_after=10)
                                break
                            else:
                                if getdupe.raw_channel_mentions:
                                    dupechannel = getdupe.raw_channel_mentions[0]
                                elif getdupe and (getdupe.content.lower() == 'cancel'):
                                    break
                                elif getdupe and (not getdupe.raw_channel_mentions):
                                    await channel.send("You didn't send me a channel mention, just type # to see a list of channels and select the duplicate channel. You can cancel with 'cancel' or I'll cancel in four minutes.", delete_after=10)
                                    continue
                            if dupechannel == channel.id:
                                await channel.send("That's this channel! Try again. You can cancel with 'cancel' or I'll cancel in four minutes.", delete_after=10)
                                continue
                            if (not self.bot.guild_dict[guild.id][report_dict][dupechannel].get('coordinates', False)):
                                self.bot.guild_dict[guild.id][report_dict][dupechannel]['coordinates'] = self.bot.guild_dict[guild.id][report_dict][channel.id]['coordinates']
                                self.bot.guild_dict[guild.id][report_dict][dupechannel]['exp'] = self.bot.guild_dict[guild.id][report_dict][channel.id]['exp']
                                self.bot.guild_dict[guild.id][report_dict][channel.id]['coordinates'] = False
                                getdupechannel = self.bot.get_channel(dupechannel)
                                oldraidmsg = await getdupechannel.fetch_message(self.bot.guild_dict[guild.id][report_dict][dupechannel]['raid_message'])
                                duperaidmsg = await channel.fetch_message(self.bot.guild_dict[guild.id][report_dict][channel.id]['raid_message'])
                                oldembed = oldraidmsg.embeds[0]
                                dupeembed = duperaidmsg.embeds[0]
                                newembed = discord.Embed(title=oldembed.title, description=oldembed.description, url=dupeembed.url, colour=guild.me.colour)
                                for field in oldembed.fields:
                                    newembed.add_field(name=field.name, value=field.value, inline=field.inline)
                                for field in dupeembed.fields:
                                    if _('expires') in field.name.lower() or _('hatches') in field.name.lower() or _('event') in field.name.lower():
                                        newembed.add_field(name=field.name, value=field.value, inline=field.inline)
                                newembed.set_footer(text=oldembed.footer.text, icon_url=oldembed.footer.icon_url)
                                newembed.set_author(name=oldembed.author.name, icon_url=oldembed.author.icon_url)
                                newembed.set_thumbnail(url=oldembed.thumbnail.url)
                                try:
                                    newraidmsg = await oldraidmsg.edit(new_content=oldraidmsg.content, embed=newembed, content=oldraidmsg.content)
                                except:
                                    pass
                                await channel.send('Settings moved!')
                                await getdupechannel.send('Settings from a duplicate bot post have been moved to this channel.')
                                break
                            else:
                                await channel.send("The channel you mentioned is already a bot channel. Try again. You can cancel with 'cancel' or I'll cancel in four minutes.", delete_after=10)
                                continue
                    return await self.expire_channel(channel)
            else:
                await utils.safe_delete(rusure)
                confirmation = await channel.send(_('Duplicate Report Timed Out.'), delete_after=10)
                logger.info((('Duplicate Report - Timeout - ' + channel.name) + ' - Report by ') + author.name)
                dupecount = 2
                self.bot.guild_dict[guild.id][report_dict][channel.id]['duplicate'] = dupecount
        else:
            rc_d['duplicate'] = dupecount
            confirmation = await channel.send(_('Duplicate report #{duplicate_report_count} received.').format(duplicate_report_count=str(dupecount)))
            logger.info((((('Duplicate Report - ' + channel.name) + ' - Report #') + str(dupecount)) + '- Report by ') + author.name)
            return

    @commands.command()
    async def counters(self, ctx, *, args = None):
        """Simulate a Raid battle with Pokebattler.

        Usage: !counters [pokemon] [weather] [user]
        See !help weather for acceptable values for weather.
        If [user] is a valid Pokebattler user id, Meowth will simulate the Raid with that user's Pokebox.
        Uses current boss and weather by default if available."""
        async with ctx.typing():
            await self._counters(ctx, args)

    async def _counters(self, ctx, args):
        report_dict = await utils.get_report_dict(ctx.bot, ctx.channel)
        rgx = '[^a-zA-Z0-9]'
        channel = ctx.channel
        guild = channel.guild
        user = self.bot.guild_dict[ctx.guild.id].get('trainers', {}).get(ctx.author.id, {}).get('pokebattlerid', None)
        weather = None
        weather_list = [_('none'), _('extreme'), _('clear'), _('sunny'), _('rainy'),
                        _('partlycloudy'), _('cloudy'), _('windy'), _('snow'), _('fog')]
        ctrs_dict = {}
        if args:
            user = next((w for w in args.split() if w.isdigit()), user)
            args = args.replace(str(user), "").strip()
            weather = next((w for w in weather_list if re.sub(rgx, '', w) in re.sub(rgx, '', args.lower())), None)
            args = args.replace(str(weather), "").strip()
        if (checks.check_raidchannel(ctx) or checks.check_exraidchannel(ctx)) and not checks.check_meetupchannel(ctx):
            pkmn = self.bot.guild_dict[guild.id][report_dict][channel.id].get('pkmn_obj', None)
            pkmn = await pkmn_class.Pokemon.async_get_pokemon(self.bot, pkmn)
            if pkmn:
                ctrs_dict = self.bot.guild_dict[guild.id][report_dict][channel.id].get('ctrs_dict', {})
                moveset = self.bot.guild_dict[guild.id][report_dict][channel.id].get('moveset', 0)
                movesetstr = ctrs_dict.get(moveset, {}).get('moveset', "Unknown Moveset")
                if ctrs_dict and not user:
                    ctrsembed = copy.deepcopy(ctrs_dict[moveset]['embed'])
                    ctrsembed.remove_field(6)
                    ctrsembed.remove_field(6)
                    return await ctx.send(embed=ctrsembed)
                if not weather:
                    weather = self.bot.guild_dict[guild.id][report_dict][channel.id].get('weather', None)
            else:
                pkmn = next((str(p) for p in self.bot.raid_list if not str(p).isdigit() and re.sub(rgx, '', str(p)) in re.sub(rgx, '', args.lower())), None)
                if not pkmn:
                    return await ctx.channel.send(_("Meowth! You're missing some details! Be sure to enter a pokemon! Usage: **!counters <pkmn> [weather] [user ID]**"), delete_after=10)
        else:
            moveset = 0
            movesetstr = "Unknown Moveset"
            pkmn, match_list = await pkmn_class.Pokemon.ask_pokemon(ctx, args)
            if not pkmn:
                return await ctx.channel.send(_("Meowth! You're missing some details! Be sure to enter a pokemon! Usage: **!counters <pkmn> [weather] [user ID]**"), delete_after=10)
        level = utils.get_level(self.bot, str(pkmn))
        redirect_url = ""
        url = f"https://fight.pokebattler.com/raids/defenders/{pkmn.game_name.upper()}{'_FORM' if pkmn.form or pkmn.region else ''}/levels/RAID_LEVEL_{level}/attackers/"
        if user:
            url += "users/{user}/".format(user=user)
            userstr = _("user #{user}'s").format(user=user)
        else:
            url += "levels/30/"
            userstr = _("Level 30")
        weather_list = [_('none'), _('extreme'), _('clear'), _('sunny'), _('rainy'),
                        _('partlycloudy'), _('cloudy'), _('windy'), _('snow'), _('snowy'), _('fog'), _('foggy')]
        match_list = ['NO_WEATHER', 'NO_WEATHER', 'CLEAR', 'CLEAR', 'RAINY',
                            'PARTLY_CLOUDY', 'OVERCAST', 'WINDY', 'SNOW', 'SNOW', 'FOG', 'FOG']
        if not weather:
            index = 0
        else:
            index = weather_list.index(weather)
        weather = match_list[index]
        url += "strategies/CINEMATIC_ATTACK_WHEN_POSSIBLE/DEFENSE_RANDOM_MC?sort=OVERALL&"
        url += "weatherCondition={weather}&dodgeStrategy=DODGE_REACTION_TIME&aggregation=AVERAGE".format(weather=weather)
        if not level:
            redirect_url = f"https://www.pokebattler.com/raids/{pkmn.name.upper()}"
            async with aiohttp.ClientSession() as sess:
                async with sess.get(redirect_url, allow_redirects=True) as resp:
                    redirect_url = str(resp.url)
                url = redirect_url.replace("/levels/35", "/levels/30")
                url = url.replace("https://www", "https://fight")
        async with aiohttp.ClientSession() as sess:
            async with sess.get(url) as resp:
                data = await resp.json(content_type=None)
        if not data or data.get('error', None):
            url = url.replace(f"{pkmn.game_name.upper()}_FORM", pkmn.name.upper())
            pkmn.form = None
            pkmn.region = None
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url) as resp:
                    data = await resp.json(content_type=None)
        if not data or data.get('error', None):
            return None
        title_url = url.replace('https://fight', 'https://www')
        hyperlink_icon = 'https://i.imgur.com/fn9E5nb.png'
        pbtlr_icon = 'https://www.pokebattler.com/favicon-32x32.png'
        if user:
            try:
                test_var = data['attackers'][0]
            except KeyError:
                await ctx.send(f"{ctx.author.mention} it looks like you haven't set up your pokebox yet! Sending you generic level 30 counters.")
                url = url.replace(f"users/{user}", 'levels/30')
                async with aiohttp.ClientSession() as sess:
                    async with sess.get(url) as resp:
                        data = await resp.json(content_type=None)

        data = data['attackers'][0]
        raid_cp = data['cp']
        atk_levels = '30'
        if movesetstr == "Unknown Moveset":
            ctrs = data['randomMove']['defenders'][-6:]
            est = data['randomMove']['total']['estimator']
        else:
            for moveset in data['byMove']:
                move1 = moveset['move1'][:-5].lower().title().replace('_', ' ')
                move2 = moveset['move2'].lower().title().replace('_', ' ')
                moveset_str = f'{move1} | {move2}'
                if moveset_str == movesetstr:
                    ctrs = moveset['defenders'][-6:]
                    est = moveset['total']['estimator']
                    break
            else:
                movesetstr = "Unknown Moveset"
                ctrs = data['randomMove']['defenders'][-6:]
                est = data['randomMove']['total']['estimator']
        def clean(txt):
            return txt.replace('_FAST', '').replace('_', ' ').title()
        title = f"{str(pkmn).title()} | {weather.replace('_', ' ').title()} | {movesetstr}"
        stats_msg = _("**CP:** {raid_cp}\n").format(raid_cp=raid_cp)
        stats_msg += _("**Weather:** {weather}\n").format(weather=clean(weather))
        stats_msg += _("**Attacker Level:** {atk_levels}").format(atk_levels=atk_levels)
        img_url = pkmn.img_url
        ctrs_embed = discord.Embed(description=f"**Weaknesses:** {pkmn.weakness_emoji}", colour=ctx.guild.me.colour)
        ctrs_embed.set_author(name=title, url=title_url, icon_url=hyperlink_icon)
        ctrs_embed.set_thumbnail(url=img_url)
        ctrs_embed.set_footer(text=_('Results courtesy of Pokebattler'), icon_url=pbtlr_icon)
        ctrindex = 1
        for ctr in reversed(ctrs):
            ctr_name = clean(ctr['pokemonId']).replace('Ho Oh', 'ho-oh')
            if "form" in ctr_name.lower():
                try:
                    ctr_type = self.bot.pkmn_info[ctr_name.split()[0].lower()]['forms'][ctr_name.split()[1].lower().replace('alola', 'alolan')]['type']
                except:
                    ctr_type = self.bot.pkmn_info[ctr_name.split()[0].lower()]['forms']['none']['type']
            else:
                ctr_type = self.bot.pkmn_info[ctr_name.split()[0].lower()]['forms']['none']['type']
            for index, type in enumerate(ctr_type):
                ctr_type[index] = utils.type_to_emoji(self.bot, type)
            ctr_emoji = ''.join(ctr_type)
            moveset = ctr['byMove'][-1]
            move1 = clean(moveset['move1'])
            move1 = f"{move1.title()} {utils.type_to_emoji(self.bot, utils.get_move_type(self.bot, move1))}"
            move2 = clean(moveset['move2'])
            move2 = f"{move2.title()} {utils.type_to_emoji(self.bot, utils.get_move_type(self.bot, move2))}"
            moves = f"{move1} | {move2}"
            name = f"{ctrindex}) {ctr_name.replace(' Form', '')} {ctr_emoji}"
            ctr_nick = clean(ctr.get('name', ''))
            ctr_cp = ctr['cp']
            name = f"{ctrindex}) - {ctr_nick.replace(' Form', '') or ctr_name.replace(' Form', '')} {ctr_emoji}"
            cpstr = _("CP")
            ctrs_embed.add_field(name=name, value=f"{cpstr}: {ctr_cp}\n{moves}")
            ctrindex += 1
        ctrs_embed.add_field(name=_("Difficulty Estimate:"), value=_("{est} Trainers").format(est=round(est, 2)), inline=True)
        ctrs_embed.add_field(name=_("Results with {userstr} attackers").format(userstr=userstr), value=_("[See your personalized results!](https://www.pokebattler.com/raids/{pkmn})").format(pkmn=pkmn.name.replace('-', '_').upper()), inline=True)
        if user:
            return await ctx.author.send(embed=ctrs_embed, delete_after=600)
        await ctx.channel.send(embed=ctrs_embed)

    async def _get_generic_counters(self, channel, pkmn, weather=None):
        guild = channel.guild
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, pkmn)
        if not pokemon:
            return
        emoji_dict = {0: u'\U00000030\U0000fe0f\U000020e3', 1: u'\U00000031\U0000fe0f\U000020e3', 2: u'\U00000032\U0000fe0f\U000020e3', 3: u'\U00000033\U0000fe0f\U000020e3', 4: u'\U00000034\U0000fe0f\U000020e3', 5: u'\U00000035\U0000fe0f\U000020e3', 6: u'\U00000036\U0000fe0f\U000020e3', 7: u'\U00000037\U0000fe0f\U000020e3', 8: u'\U00000038\U0000fe0f\U000020e3', 9: u'\U00000039\U0000fe0f\U000020e3', 10: u'\U0001f51f'}
        for guild_id in list(self.bot.guild_dict.keys()):
            for raid_id in list(self.bot.guild_dict[guild_id]['raidchannel_dict'].keys()):
                if raid_id == channel.id:
                    continue
                if self.bot.guild_dict[guild_id]['raidchannel_dict'][raid_id].get('pkmn_obj') == str(pokemon):
                    ctrs_dict = self.bot.guild_dict[guild_id]['raidchannel_dict'][raid_id].get('ctrs_dict', {})
                    if not ctrs_dict:
                        continue
                    ctr_weather = ctrs_dict[0].get('weather')
                    if ctr_weather == str(weather):
                        return ctrs_dict
        entered_weather = str(weather)
        ctrs_dict = {}
        ctrs_index = 0
        ctrs_dict[ctrs_index] = {}
        ctrs_dict[ctrs_index]['moveset'] = "Unknown Moveset"
        ctrs_dict[ctrs_index]['emoji'] = '0\u20e3'
        img_url = pokemon.img_url
        level = utils.get_level(self.bot, str(pokemon)) if utils.get_level(self.bot, str(pokemon)).isdigit() else "5"
        weather_list = [_('none'), _('extreme'), _('clear'), _('sunny'), _('rainy'),
                        _('partlycloudy'), _('cloudy'), _('windy'), _('snow'), _('snowy'), _('fog'), _('foggy')]
        match_list = ['NO_WEATHER', 'NO_WEATHER', 'CLEAR', 'CLEAR', 'RAINY',
                            'PARTLY_CLOUDY', 'OVERCAST', 'WINDY', 'SNOW', 'SNOW', 'FOG', 'FOG']
        if not weather:
            index = 0
        else:
            index = weather_list.index(weather)
        weather = match_list[index]
        url = f"https://fight.pokebattler.com/raids/defenders/{pokemon.game_name.upper()}{'_FORM' if pokemon.form or pokemon.region else ''}/levels/RAID_LEVEL_{level}/attackers/"
        url += "levels/30/"
        url += "strategies/CINEMATIC_ATTACK_WHEN_POSSIBLE/DEFENSE_RANDOM_MC?sort=OVERALL&"
        url += "weatherCondition={weather}&dodgeStrategy=DODGE_REACTION_TIME&aggregation=AVERAGE".format(weather=weather)
        title_url = url.replace('https://fight', 'https://www')
        hyperlink_icon = 'https://i.imgur.com/fn9E5nb.png'
        pbtlr_icon = 'https://www.pokebattler.com/favicon-32x32.png'
        async with aiohttp.ClientSession() as sess:
            async with sess.get(url) as resp:
                data = await resp.json(content_type=None)
        if not data or data.get('error', None):
            url = url.replace(f"{str(pokemon.game_name).upper()}_FORM", pokemon.name.upper())
            pokemon.form = None
            pokemon.region = None
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url) as resp:
                    data = await resp.json(content_type=None)
        if not data or data.get('error', None):
            return {}
        data = data['attackers'][0]
        raid_cp = data['cp']
        atk_levels = '30'
        ctrs = data['randomMove']['defenders'][-6:]
        def clean(txt):
            return txt.replace('_FAST', '').replace('_', ' ').title()
        title = f"{str(pokemon).title()} | {weather.replace('_', ' ').title()} | Unknown Moveset"
        stats_msg = _("**CP:** {raid_cp}\n").format(raid_cp=raid_cp)
        stats_msg += _("**Weather:** {weather}\n").format(weather=clean(weather))
        stats_msg += _("**Attacker Level:** {atk_levels}").format(atk_levels=atk_levels)
        ctrs_embed = discord.Embed(description=f"**Weaknesses:** {pokemon.weakness_emoji}", colour=guild.me.colour)
        ctrs_embed.set_author(name=title, url=title_url, icon_url=hyperlink_icon)
        ctrs_embed.set_thumbnail(url=img_url)
        ctrs_embed.set_footer(text=_('Results courtesy of Pokebattler'), icon_url=pbtlr_icon)
        ctrindex = 1
        for ctr in reversed(ctrs):
            ctr_name = clean(ctr['pokemonId']).replace('Ho Oh', 'ho-oh')
            if "form" in ctr_name.lower():
                try:
                    ctr_type = self.bot.pkmn_info[ctr_name.split()[0].lower()]['forms'][ctr_name.split()[1].lower().replace('alola', 'alolan')]['type']
                except:
                    ctr_type = self.bot.pkmn_info[ctr_name.split()[0].lower()]['forms']['none']['type']
            else:
                ctr_type = self.bot.pkmn_info[ctr_name.split()[0].lower()]['forms']['none']['type']
            for index, type in enumerate(ctr_type):
                ctr_type[index] = utils.type_to_emoji(self.bot, type)
            ctr_emoji = ''.join(ctr_type)
            moveset = ctr['byMove'][-1]
            move1 = clean(moveset['move1'])
            move1 = f"{move1.title()} {utils.type_to_emoji(self.bot, utils.get_move_type(self.bot, move1))}"
            move2 = clean(moveset['move2'])
            move2 = f"{move2.title()} {utils.type_to_emoji(self.bot, utils.get_move_type(self.bot, move2))}"
            moves = f"{move1} | {move2}"
            name = f"{ctrindex}) {ctr_name.replace(' Form', '')} {ctr_emoji}"
            ctrs_embed.add_field(name=name, value=moves)
            ctrindex += 1
        ctrs_dict[ctrs_index]['embed'] = ctrs_embed
        ctrs_dict[ctrs_index]['estimator'] = str(round(data['randomMove']['total']['estimator'], 2)) + " Trainers"
        for moveset in data['byMove']:
            est = str(round(moveset['total']['estimator'], 2)) + " Trainers"
            ctrs_index += 1
            if ctrs_index == 11:
                break
            move1 = moveset['move1'][:-5].title().replace('_', ' ')
            move2 = moveset['move2'].title().replace('_', ' ')
            movesetstr = f'{move1} | {move2}'
            ctrs = moveset['defenders'][-6:]
            title = f"{str(pokemon).title()} | {weather.replace('_', ' ').title()} | {movesetstr}"
            ctrs_embed = discord.Embed(description=f"**Weaknesses:** {pokemon.weakness_emoji}", colour=guild.me.colour)
            ctrs_embed.set_author(name=title, url=title_url, icon_url=hyperlink_icon)
            ctrs_embed.set_thumbnail(url=img_url)
            ctrs_embed.set_footer(text=_('Results courtesy of Pokebattler'), icon_url=pbtlr_icon)
            ctrindex = 1
            for ctr in reversed(ctrs):
                ctr_name = clean(ctr['pokemonId']).replace('Ho Oh', 'ho-oh')
                if "form" in ctr_name.lower():
                    try:
                        ctr_type = self.bot.pkmn_info[ctr_name.split()[0].lower()]['forms'][ctr_name.split()[1].lower().replace('alola', 'alolan')]['type']
                    except:
                        ctr_type = self.bot.pkmn_info[ctr_name.split()[0].lower()]['forms']['none']['type']
                else:
                    ctr_type = self.bot.pkmn_info[ctr_name.split()[0].lower()]['forms']['none']['type']
                for index, type in enumerate(ctr_type):
                    ctr_type[index] = utils.type_to_emoji(self.bot, type)
                ctr_emoji = ''.join(ctr_type)
                moveset = ctr['byMove'][-1]
                move1 = clean(moveset['move1'])
                move1 = f"{move1.title()} {utils.type_to_emoji(self.bot, utils.get_move_type(self.bot, move1))}"
                move2 = clean(moveset['move2'])
                move2 = f"{move2.title()} {utils.type_to_emoji(self.bot, utils.get_move_type(self.bot, move2))}"
                moves = f"{move1} | {move2}"
                name = f"{ctrindex}) - {ctr_name.replace(' Form', '')} {ctr_emoji}"
                ctrs_embed.add_field(name=name, value=moves)
                ctrindex += 1
            ctrs_dict[ctrs_index] = {'moveset': movesetstr, 'embed': ctrs_embed, 'emoji': emoji_dict[ctrs_index], 'estimator': est}
        moveset_list = []
        for moveset in ctrs_dict:
            if 'Unknown Moveset' in ctrs_dict[moveset]['moveset']:
                moveset_list.append(f"{ctrs_dict[moveset]['emoji']}: {ctrs_dict[moveset]['moveset']}\n")
            else:
                moves = ctrs_dict[moveset]['moveset'].split('|')
                moves = [x.lower().strip() for x in moves]
                moves = [f"{x.title()} {utils.type_to_emoji(self.bot, utils.get_move_type(self.bot, x))}" for x in moves if x != "unknown moveset"]
                moveset_list.append(f"{ctrs_dict[moveset]['emoji']}: {moves[0]} | {moves[1]}\n")
        for moveset in ctrs_dict:
            ctrs_split = int(round(len(moveset_list)/2+0.1))
            ctrs_dict[moveset]['embed'].add_field(name=_("**Possible Movesets:**"), value=f"{''.join(moveset_list[:ctrs_split])}", inline=True)
            ctrs_dict[moveset]['embed'].add_field(name=_('**Possible Movesets:**'), value=f"{''.join(moveset_list[ctrs_split:])}", inline=True)
            ctrs_dict[moveset]['embed'].add_field(name="Difficulty Estimate", value=ctrs_dict[moveset]['estimator'], inline=True)
            ctrs_dict[moveset]['embed'].add_field(name=_("Results with Level 30 attackers"), value=_("[See your personalized results!](https://www.pokebattler.com/raids/{pkmn})").format(pkmn=pokemon.name.replace('-', '_').upper()), inline=True)
        ctrs_dict[0]['weather'] = entered_weather
        return ctrs_dict

    @commands.command()
    @checks.activeraidchannel()
    async def weather(self, ctx, *, weather=None):
        """Sets the weather for the raid.
        Usage: !weather <weather>
        Only usable in raid channels.
        Acceptable options: none, extreme, clear, rainy, partlycloudy, cloudy, windy, snowy, foggy"""
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
        report_dict = await utils.get_report_dict(ctx.bot, ctx.channel)
        weather_list = [_('none'), _('extreme'), _('clear'), _('sunny'), _('rainy'),
                        _('partly cloudy'), _('cloudy'), _('windy'), _('snowy'), _('foggy')]
        weather_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/weatherIcon_large_extreme.png?cache=1")
        async with ctx.typing():
            if not weather:
                def check(reply):
                    if reply.author is not ctx.guild.me and reply.channel.id == ctx.channel.id and reply.author == ctx.message.author:
                        return True
                    else:
                        return False
                while True:
                    raid_coordinates = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].get('coordinates', None)
                    auto_weather = None
                    if raid_coordinates:
                        auto_weather = await self.auto_weather(ctx, raid_coordinates)
                    weather_embed.clear_fields()
                    weather_embed.add_field(name=_('**Edit Channel Weather**'), value=f"Meowth! I will help you edit the channel weather! Reply with the current weather from the following list: **{', '.join(weather_list)}**. You can reply with **cancel** to stop anytime.\n\n{'I think the current weather is: **'+auto_weather+'**' if auto_weather else ''}", inline=False)
                    weather_wait = await ctx.send(embed=weather_embed)
                    try:
                        weather_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        weather_msg = None
                    await utils.safe_delete(weather_wait)
                    if not weather_msg:
                        weather_embed.clear_fields()
                        weather_embed.add_field(name=f"**Edit Channel Weather**", value=f"Meowth! Your report has been cancelled because you took too long to respond! Retry when you're ready.")
                        return await ctx.send(embed=weather_embed, delete_after=30)
                    else:
                        await utils.safe_delete(weather_msg)
                    if weather_msg.clean_content.lower() == "cancel":
                        weather_embed.clear_fields()
                        weather_embed.add_field(name=f"**Edit Channel Weather**", value=f"Meowth! Your report has been cancelled because you cancelled the report! Retry when you're ready.")
                        return await ctx.send(embed=weather_embed, delete_after=30)
                    elif weather_msg.clean_content.lower() not in weather_list:
                        weather_embed.clear_fields()
                        weather_embed.add_field(name=f"**Edit Channel Weather**", value=f"Meowth! Your report has been cancelled because you entered an invalid option! Retry when you're ready.")
                        await ctx.send(embed=weather_embed, delete_after=30)
                        continue
                    else:
                        weather = weather_msg.clean_content.lower()
                        break
            if "rain" in weather.lower():
                weather = "rainy"
            elif "partly" in weather.lower():
                weather = "partlycloudy"
            elif "clear" in weather.lower() or "sunny" in weather.lower():
                weather = "clear"
            elif "cloudy" in weather.lower() or "overcast" in weather.lower():
                weather = "cloudy"
            elif "wind" in weather.lower():
                weather = "windy"
            elif "snow" in weather.lower():
                weather = "snowy"
            elif "fog" in weather.lower():
                weather = "foggy"
            elif "none" in weather.lower() or "extreme" in weather.lower():
                weather = None
            pokemon = None
            pkmn = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].get('pkmn_obj', None)
            if pkmn:
                pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, pkmn)
                pokemon.weather = weather
            weather_embed.clear_fields()
            if pkmn:
                weather_embed.add_field(name=f"**Channel Weather**", value=f"The weather is currently set to {str(weather).replace('partlycloudy', 'partly cloudy')}. If this changes you can set the correct weather using **{ctx.prefix}weather**.\n\n{'**Boosted**: ' + ('').join([utils.type_to_emoji(self.bot, x) for x in utils.get_weather_boost(str(weather))]) if weather else ''}\n\n{str(pokemon)+' is ***boosted*** in '+str(weather)+' weather.' if pokemon.is_boosted else ''}")
            else:
                weather_embed.add_field(name=f"**Channel Weather**", value=f"The weather is currently set to {str(weather).replace('partlycloudy', 'partly cloudy')}. If this changes you can set the correct weather using **{ctx.prefix}weather**.\n\n{'**Boosted**: ' + ('').join([utils.type_to_emoji(self.bot, x) for x in utils.get_weather_boost(str(weather))]) if weather else ''}")
            if weather:
                weather_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/weatherIcon_large_{str(weather).lower()}{'Day' if now.hour >= 6 and now.hour < 18 else 'Night'}.png?cache=1")
            try:
                weather_msg = await ctx.channel.fetch_message(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['weather_msg'])
                await weather_msg.edit(embed=weather_embed)
            except:
                pass
            await ctx.channel.send(embed=weather_embed, delete_after=30)
            if pokemon:
                try:
                    raid_message = await ctx.channel.fetch_message(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['raid_message'])
                    report_channel = self.bot.get_channel(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['report_channel'])
                    report_message = await report_channel.fetch_message(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['raid_report'])
                    raid_embed = raid_message.embeds[0]
                    if pokemon.is_boosted or "boosted" in raid_embed.fields[0].value.lower():
                        index = 0
                        for field in raid_embed.fields:
                            if _("**Details:**") in field.name:
                                raid_embed.set_field_at(index, name=_("**Details:**"), value=f"{field.value.splitlines()[0]}\n{pokemon.is_boosted if pokemon.is_boosted else ''}", inline=field.inline)
                                break
                            else:
                                index += 1
                        await raid_message.edit(embed=raid_embed)
                        await report_message.edit(embed=raid_embed)
                except Exception as e:
                    print(traceback.format_exc())
                ctrs_dict = await self._get_generic_counters(ctx.channel, pkmn, weather.lower())
                if str(utils.get_level(self.bot, pkmn)) in self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('counters', {}).get('auto_levels', []):
                    try:
                        ctrsmessage = await ctx.channel.fetch_message(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['ctrsmessage'])
                        moveset = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['moveset']
                        newembed = ctrs_dict[moveset]['embed']
                        await ctrsmessage.edit(embed=newembed)
                    except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, KeyError):
                        pass
                    self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['ctrs_dict'] = ctrs_dict
            self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['weather'] = weather

    """
    Status Management
    """

    async def _party_status(self, ctx, total, teamcounts):
        channel = ctx.channel
        author = ctx.author
        for role in ctx.author.roles:
            if role.name.lower() == 'mystic':
                my_team = 'mystic'
                break
            elif role.name.lower() == 'valor':
                my_team = 'valor'
                break
            elif role.name.lower() == 'instinct':
                my_team = 'instinct'
                break
        else:
            my_team = 'unknown'
        if not teamcounts:
            teamcounts = "1"
        teamcounts = teamcounts.lower().split()
        if total and teamcounts[0].isdigit():
            del teamcounts[0]
        mystic = ['mystic', 0]
        instinct = ['instinct', 0]
        valor = ['valor', 0]
        unknown = ['unknown', 0]
        team_aliases = {
            'mystic': mystic,
            'blue': mystic,
            'm': mystic,
            'b': mystic,
            'instinct': instinct,
            'yellow': instinct,
            'i': instinct,
            'y': instinct,
            'valor': valor,
            'red': valor,
            'v': valor,
            'r': valor,
            'unknown': unknown,
            'grey': unknown,
            'gray': unknown,
            'u': unknown,
            'g': unknown,
        }
        regx = re.compile('([a-zA-Z]+)([0-9]+)|([0-9]+)([a-zA-Z]+)')
        for count in teamcounts:
            if count.isdigit():
                if total:
                    return await channel.send(_('Only one non-team count can be accepted.'), delete_after=10)
                else:
                    total = int(count)
            else:
                match = regx.match(count)
                if match:
                    match = regx.match(count).groups()
                    str_match = match[0] or match[3]
                    int_match = match[1] or match[2]
                    if str_match in team_aliases.keys():
                        if int_match:
                            if team_aliases[str_match][1]:
                                return await channel.send(_('Only one count per team accepted.'), delete_after=10)
                            else:
                                team_aliases[str_match][1] = int(int_match)
                                continue
                return await channel.send(_('Invalid format, please check and try again.'), delete_after=10)
        team_total = ((mystic[1] + instinct[1]) + valor[1]) + unknown[1]
        if total:
            if int(team_total) > int(total):
                a = _('Team counts are higher than the total, double check your counts and try again. You entered **')
                b = _('** total and **')
                c = _('** in your party.')
                return await channel.send(((( a + str(total)) + b) + str(team_total)) + c, delete_after=10)
            if int(total) > int(team_total):
                if team_aliases[my_team][1]:
                    if unknown[1]:
                        return await channel.send(_('Meowth! Something is not adding up! Try making sure your total matches what each team adds up to!'), delete_after=10)
                    unknown[1] = total - team_total
                else:
                    team_aliases[my_team][1] = total - team_total
        partylist = {'mystic':mystic[1], 'valor':valor[1], 'instinct':instinct[1], 'unknown':unknown[1]}
        result = [total, partylist]
        return result

    async def _get_party(self, channel, author=None):
        report_dict = await utils.get_report_dict(self.bot, channel)
        egg_level = self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['egg_level']
        boss_dict = {}
        boss_list = []
        if egg_level != "0":
            for boss in self.bot.raid_dict[str(egg_level)]:
                if isinstance(boss, pkmn_class.Pokemon):
                    boss_list.append(str(boss).lower())
                    boss_dict[str(boss).lower()] = {
                        "type": boss.emoji,
                        "weakness":boss.weakness_emoji,
                        "total": 0
                    }
        channel_dict = {"mystic":0, "valor":0, "instinct":0, "unknown":0, "maybe":0, "coming":0, "here":0, "lobby":0, "total":0, "boss":0}
        team_list = ["mystic", "valor", "instinct", "unknown"]
        status_list = ["maybe", "coming", "here", "lobby"]
        trainer_dict = copy.deepcopy(self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['trainer_dict'])
        for trainer in trainer_dict:
            user = channel.guild.get_member(trainer)
            if not user:
                continue
            for team in team_list:
                channel_dict[team] += int(trainer_dict[trainer].get('party', {}).get(team, 0))
            for status in status_list:
                if trainer_dict[trainer]['status'][status]:
                    channel_dict[status] += int(trainer_dict[trainer]['count'])
            if trainer_dict[trainer].get('train', False):
                channel_dict['train'] = True
            if egg_level != "0":
                for boss in boss_list:
                    if boss.lower() in trainer_dict[trainer].get('interest', []):
                        boss_dict[boss]['total'] += int(trainer_dict[trainer]['count'])
                        channel_dict["boss"] += int(trainer_dict[trainer]['count'])
        channel_dict["total"] = channel_dict["maybe"] + channel_dict["coming"] + channel_dict["here"] + channel_dict["lobby"]
        return channel_dict, boss_dict

    async def _edit_party(self, channel, author=None):
        report_dict = await utils.get_report_dict(self.bot, channel)
        egg_level = self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['egg_level']
        pokemon = self.bot.guild_dict[channel.guild.id][report_dict][channel.id].get('pkmn_obj')
        report_message = self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['report_message']
        raid_report = self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['raid_report']
        channel_dict, boss_dict = await self._get_party(channel, author)
        display_list = []
        if egg_level != "0":
            for boss in self.bot.raid_dict[str(egg_level)]:
                if isinstance(boss, pkmn_class.Pokemon):
                    shiny_str = ""
                    if boss and "raid" in boss.shiny_available:
                        shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
                    if boss_dict[str(boss).lower()]['total'] > 0:
                        bossstr = f"{shiny_str}{str(boss).title()} {boss_dict[str(boss).lower()]['type']} : **{boss_dict[str(boss).lower()]['total']}**"
                        display_list.append(bossstr)
                    elif boss_dict[str(boss).lower()]['total'] == 0:
                        bossstr = f"{shiny_str}{str(boss).title()} {boss_dict[str(boss).lower()]['type']}"
                        display_list.append(bossstr)
        reportchannel = self.bot.get_channel(self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['report_channel'])
        try:
            reportmsg = await reportchannel.fetch_message(self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['raid_report'])
        except:
            pass
        try:
            raidmsg = await channel.fetch_message(self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['raid_message'])
        except:
            async for message in channel.history(limit=500, oldest_first=True):
                if author and message.author.id == channel.guild.me.id:
                    c = _('Coordinate here')
                    if c in message.content:
                        reportchannel = message.raw_channel_mentions[0]
                        raidmsg = message
                        break
        reportembed = raidmsg.embeds[0]
        newembed = discord.Embed(title=reportembed.title, description=reportembed.description, url=reportembed.url, colour=channel.guild.me.colour)
        if not self.bot.guild_dict[channel.guild.id].get(report_dict, {}).get(channel.id, {}).get('meetup', {}):
            if egg_level == "0":
                for field in reportembed.fields:
                    if _('weakness') in field.name.lower() or _('details') in field.name.lower():
                        newembed.add_field(name=field.name, value=field.value, inline=field.inline)
            else:
                if pokemon:
                    newembed.add_field(name=_("**Boss Interest:**") if channel_dict["boss"] > 0 else _("**Possible Bosses:**"), value=_('{bosslist1}').format(bosslist1='\n'.join(display_list)), inline=True)
                    newembed.add_field(name=_('**Weaknesses:**'), value=_('{weakness_list}\u200b').format(weakness_list=boss_dict[str(pokemon).lower()]['weakness']), inline=True)
                elif len(boss_dict.keys()) == 1:
                    for boss in self.bot.raid_dict[str(egg_level)]:
                        if isinstance(boss, pkmn_class.Pokemon):
                            break
                    newembed.add_field(name=_("**Boss Interest:**") if channel_dict["boss"] > 0 else _("**Possible Bosses:**"), value=_('{bosslist1}').format(bosslist1='\n'.join(display_list)), inline=True)
                    newembed.add_field(name=_('**Weaknesses:**'), value=_('{weakness_list}\u200b').format(weakness_list=boss_dict[str(boss).lower()]['weakness']), inline=True)
                elif len(boss_dict.keys()) > 1:
                    newembed.add_field(name=_("**Boss Interest:**") if channel_dict["boss"] > 0 else _("**Possible Bosses:**"), value=_('{bosslist1}').format(bosslist1='\n'.join(display_list[::2])), inline=True)
                    newembed.add_field(name=_("**Boss Interest:**") if channel_dict["boss"] > 0 else _("**Possible Bosses:**"), value=_('{bosslist2}').format(bosslist2='\n'.join(display_list[1::2])), inline=True)
                else:
                    newembed.add_field(name=_("**Boss Interest:**") if channel_dict["boss"] > 0 else _("**Possible Bosses:**"), value=_('{bosslist}').format(bosslist=''.join(display_list)), inline=True)
                    newembed.add_field(name=_('**Weaknesses:**'), value='\u200b', inline=True)
        for field in reportembed.fields:
            if _('possible') not in field.name.lower() and _('weakness') not in field.name.lower() and _('details') not in field.name.lower() and _('interest') not in field.name.lower() and _('list') not in field.name.lower():
                newembed.add_field(name=field.name, value=field.value, inline=field.inline)
        if channel_dict["total"] > 0:
            newembed.add_field(name=_('**Status List:**'), value=_('Maybe: **{channelmaybe}** | Coming: **{channelcoming}** | Here: **{channelhere}**').format(channelmaybe=channel_dict["maybe"], channelcoming=channel_dict["coming"], channelhere=channel_dict["here"]), inline=True)
            newembed.add_field(name=_('**Team List:**'), value='{blue_emoji}: **{channelblue}** | {red_emoji}: **{channelred}** | {yellow_emoji}: **{channelyellow}** | {grey_emoji}: **{channelunknown}**'.format(blue_emoji=utils.parse_emoji(channel.guild, self.bot.config.team_dict['mystic']), channelblue=channel_dict["mystic"], red_emoji=utils.parse_emoji(channel.guild, self.bot.config.team_dict['valor']), channelred=channel_dict["valor"], yellow_emoji=utils.parse_emoji(channel.guild, self.bot.config.team_dict['instinct']), channelyellow=channel_dict["instinct"], grey_emoji=utils.parse_emoji(channel.guild, self.bot.config.unknown), channelunknown=channel_dict["unknown"]), inline=True)
        newembed.set_footer(text=reportembed.footer.text, icon_url=reportembed.footer.icon_url)
        newembed.set_thumbnail(url=f"{reportembed.thumbnail.url.split('&report_message=')[0]}&report_message={report_message}&raid_report={raid_report}")
        newembed.set_author(name=reportembed.author.name, icon_url=reportembed.author.icon_url)
        try:
            await reportmsg.edit(embed=newembed)
        except:
            pass
        try:
            await raidmsg.edit(embed=newembed)
        except:
            pass

    @commands.command(aliases=['i', 'maybe'])
    @checks.rsvpchannel()
    async def interested(self, ctx, *, party_info: str=None):
        """Indicate you are interested in the raid.

        Usage: !interested [count] [party]
        Works only in raid channels. If count is omitted, assumes you are a group of 1.
        Otherwise, this command expects at least one word in your message to be a number,
        and will assume you are a group with that many people.

        Party is also optional. Format is #m #v #i #u to tell your party's teams."""
        await self._rsvp(ctx, "maybe", party_info)

    @commands.command(aliases=['c'])
    @checks.rsvpchannel()
    async def coming(self, ctx, *, party_info: str=None):
        """Indicate you are on the way to a raid.

        Usage: !coming [count] [party]
        Works only in raid channels. If count is omitted, checks for previous !maybe
        command and takes the count from that. If it finds none, assumes you are a group
        of 1.
        Otherwise, this command expects at least one word in your message to be a number,
        and will assume you are a group with that many people.

        Party is also optional. Format is #m #v #i #u to tell your party's teams."""
        await self._rsvp(ctx, "coming", party_info)

    @commands.command(aliases=['h'])
    @checks.rsvpchannel()
    async def here(self, ctx, *, party_info: str=None):
        """Indicate you have arrived at the raid.

        Usage: !here [count] [party]
        Works only in raid channels. If message is omitted, and
        you have previously issued !coming, then preserves the count
        from that command. Otherwise, assumes you are a group of 1.
        Otherwise, this command expects at least one word in your message to be a number,
        and will assume you are a group with that many people.

        Party is also optional. Format is #m #v #i #u to tell your party's teams."""
        await self._rsvp(ctx, "here", party_info)

    @commands.command()
    @checks.activeraidchannel()
    async def lobby(self, ctx, *, party_info: str=None):
        """Indicate you are entering the raid lobby.

        Usage: !lobby [count] [party]
        Works only in raid channels. If message is omitted, and
        you have previously issued !coming, then preserves the count
        from that command. Otherwise, assumes you are a group of 1.
        Otherwise, this command expects at least one word in your message to be a number,
        and will assume you are a group with that many people.

        Party is also optional. Format is #m #v #i #u to tell your party's teams."""
        await self._rsvp(ctx, "lobby", party_info)

    @commands.command(aliases=["sub"])
    @checks.rsvpchannel()
    async def subscribe(self, ctx):
        """Subscribe to a channel and receive alerts for any RSVPs."""
        report_dict = await utils.get_report_dict(self.bot, ctx.channel)
        alert_list = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].setdefault('alert_list', [])
        alert_emoji = self.bot.custom_emoji.get('alert_emoji', u'\U0001f514')
        if ctx.author.id not in alert_list:
            self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['alert_list'].append(ctx.author.id)
            return await ctx.send(f"{alert_emoji} - {ctx.author.mention} you are now subscribed to this channel and will receive DM alerts for any RSVPs.")

    @commands.command(aliases=["unsub"])
    @checks.rsvpchannel()
    async def unsubscribe(self, ctx):
        """unsubscribe from a channel and stop receiving alerts for any RSVPs."""
        report_dict = await utils.get_report_dict(self.bot, ctx.channel)
        alert_list = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].setdefault('alert_list', [])
        alert_emoji = self.bot.custom_emoji.get('alert_emoji', u'\U0001f515')
        if ctx.author.id in alert_list:
            self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['alert_list'].remove(ctx.author.id)
            return await ctx.send(f"{alert_emoji} - {ctx.author.mention} you are no longer subscribed to this channel and will not receive DM alerts for any RSVPs.")

    @commands.command()
    @checks.rsvpchannel()
    async def rsvp(self, ctx):
        """RSVP (interested, coming, here, lobby) for the current channel."""
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        report_dict = await utils.get_report_dict(self.bot, ctx.channel)
        rsvp_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/unicode_speechballoon.png?cache=1')
        rsvp_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=ctx.author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=ctx.author.avatar_url_as(format=None, static_format='jpg', size=32))
        lobby = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].get('lobby', None)
        def check(reply):
            if reply.author is not ctx.guild.me and reply.channel.id == ctx.channel.id and reply.author == ctx.message.author:
                return True
            else:
                return False
        while True:
            async with ctx.typing():
                rsvp_embed.clear_fields()
                rsvp_embed.add_field(name=_('**Set RSVP Status**'), value=f"Meowth! I'll help you set your status in this channel!\n\nReply with your status from the following:\n**interested** - You are interested in this but can't commit.\n**coming** - You are on your way.\n**here** - You are at the location and ready\n**cancel** - You are no longer interested\n{'**lobby** - You are joining the raid lobby (raids only).' if lobby else ''}\n\nYou can reply with **exit** to stop anytime.", inline=False)
                rsvp_wait = await ctx.send(embed=rsvp_embed)
                try:
                    rsvp_msg = await self.bot.wait_for('message', timeout=60, check=check)
                except asyncio.TimeoutError:
                    rsvp_msg = None
                await utils.safe_delete(rsvp_wait)
                if not rsvp_msg:
                    rsvp_embed.clear_fields()
                    rsvp_embed.add_field(name=_('**RSVP Cancelled**'), value=_("Meowth! Your RSVP has been cancelled because you took too long to respond! Retry when you're ready."), inline=False)
                    return await ctx.send(embed=rsvp_embed, delete_after=10)
                else:
                    await utils.safe_delete(rsvp_msg)
                if rsvp_msg.clean_content.lower() == "exit":
                    rsvp_embed.clear_fields()
                    rsvp_embed.add_field(name=_('**RSVP Cancelled**'), value=_("Meowth! Your RSVP has been cancelled because you cancelled the report! Retry when you're ready."), inline=False)
                    return await ctx.send(embed=rsvp_embed, delete_after=10)
                else:
                    rsvp_type = rsvp_msg.clean_content.lower()
                    if not any([rsvp_type == "interested", rsvp_type == "coming", rsvp_type == "here", rsvp_type == "cancel", rsvp_type == "lobby"]):
                        rsvp_embed.clear_fields()
                        rsvp_embed.add_field(name=_('**RSVP Cancelled**'), value=_("Meowth! Your RSVP has been cancelled because you entered an invalid option! Retry when you're ready."), inline=False)
                        return await ctx.send(embed=rsvp_embed, delete_after=10)
                if rsvp_type == "cancel":
                    return await self._cancel(ctx)
                elif rsvp_type == "lobby":
                    if lobby:
                        return await self._rsvp(ctx, "lobby", "1")
                    else:
                        rsvp_embed.clear_fields()
                        rsvp_embed.add_field(name=_('**RSVP Cancelled**'), value=_("Meowth! Your RSVP has been cancelled because you entered an invalid option! Retry when you're ready."), inline=False)
                        return await ctx.send(embed=rsvp_embed, delete_after=10)
                rsvp_embed.clear_fields()
                rsvp_embed.add_field(name=_('**Set RSVP Status**'), value=f"Meowth! Next, I'll need to know your **party count**. Reply with the amount of people in your party. If it is just you, reply with **1**. You can reply with **exit** to stop anytime.", inline=False)
                rsvp_wait = await ctx.send(embed=rsvp_embed)
                party_count = 1
                try:
                    rsvp_msg = await self.bot.wait_for('message', timeout=60, check=check)
                except asyncio.TimeoutError:
                    rsvp_msg = None
                await utils.safe_delete(rsvp_wait)
                if not rsvp_msg:
                    rsvp_embed.clear_fields()
                    rsvp_embed.add_field(name=_('**RSVP Cancelled**'), value=_("Meowth! Your RSVP has been cancelled because you took too long to respond! Retry when you're ready."), inline=False)
                    return await ctx.send(embed=rsvp_embed, delete_after=10)
                else:
                    await utils.safe_delete(rsvp_msg)
                if rsvp_msg.clean_content.lower() == "exit":
                    rsvp_embed.clear_fields()
                    rsvp_embed.add_field(name=_('**RSVP Cancelled**'), value=_("Meowth! Your RSVP has been cancelled because you cancelled the report! Retry when you're ready."), inline=False)
                    return await ctx.send(embed=rsvp_embed, delete_after=10)
                else:
                    party_count = rsvp_msg.clean_content.lower()
                    if not party_count.isdigit():
                        rsvp_embed.clear_fields()
                        rsvp_embed.add_field(name=_('**RSVP Cancelled**'), value=_("Meowth! Your RSVP has been cancelled because you entered an invalid option! Retry when you're ready."), inline=False)
                        return await ctx.send(embed=rsvp_embed, delete_after=10)
                party_teams = ""
                if int(party_count) > 1:
                    rsvp_embed.clear_fields()
                    rsvp_embed.add_field(name=_('**Set RSVP Status**'), value=f"Meowth! Next, I'll need to know your **team counts**. If everybody in your party is in the same team, reply with **same**. Otherwise, build a message like this: **2m 3v** where m = mystic count, v = valor count, and i = instinct count. You can reply with **exit** to stop anytime.", inline=False)
                    rsvp_wait = await ctx.send(embed=rsvp_embed)
                    try:
                        rsvp_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        rsvp_msg = None
                    await utils.safe_delete(rsvp_wait)
                    if not rsvp_msg:
                        rsvp_embed.clear_fields()
                        rsvp_embed.add_field(name=_('**RSVP Cancelled**'), value=_("Meowth! Your RSVP has been cancelled because you took too long to respond! Retry when you're ready."), inline=False)
                        return await ctx.send(embed=rsvp_embed, delete_after=10)
                    else:
                        await utils.safe_delete(rsvp_msg)
                    if rsvp_msg.clean_content.lower() == "exit":
                        rsvp_embed.clear_fields()
                        rsvp_embed.add_field(name=_('**RSVP Cancelled**'), value=_("Meowth! Your RSVP has been cancelled because you cancelled the report! Retry when you're ready."), inline=False)
                        return await ctx.send(embed=rsvp_embed, delete_after=10)
                    else:
                        if rsvp_msg.clean_content.lower() != "same":
                            party_teams = rsvp_msg.clean_content.lower()
                entered_interest = ""
                if "raid" in report_dict:
                    egg_level = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].get('egg_level')
                    if len(self.bot.raid_info['raid_eggs'][egg_level]['pokemon']) > 1 and self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].get('type') == "egg":
                        rsvp_embed.clear_fields()
                        rsvp_embed.add_field(name=_('**Set RSVP Status**'), value=f"Meowth! Next, Do you have any specific pokemon you are interested in? Reply with either **no** or a comma separated list of {', '.join(self.bot.raid_info['raid_eggs'][egg_level]['pokemon'])}. You can reply with **exit** to stop anytime.", inline=False)
                        rsvp_wait = await ctx.send(embed=rsvp_embed)
                        try:
                            rsvp_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            rsvp_msg = None
                        await utils.safe_delete(rsvp_wait)
                        if not rsvp_msg:
                            rsvp_embed.clear_fields()
                            rsvp_embed.add_field(name=_('**RSVP Cancelled**'), value=_("Meowth! Your RSVP has been cancelled because you took too long to respond! Retry when you're ready."), inline=False)
                            return await ctx.send(embed=rsvp_embed, delete_after=10)
                        else:
                            await utils.safe_delete(rsvp_msg)
                        if rsvp_msg.clean_content.lower() == "exit":
                            rsvp_embed.clear_fields()
                            rsvp_embed.add_field(name=_('**RSVP Cancelled**'), value=_("Meowth! Your RSVP has been cancelled because you cancelled the report! Retry when you're ready."), inline=False)
                            return await ctx.send(embed=rsvp_embed, delete_after=10)
                        else:
                            if rsvp_msg.clean_content.lower() != "no":
                                entered_interest = rsvp_msg.clean_content.lower()
                    break
        party_info = f"{party_count} {party_teams} {entered_interest}"
        await self._rsvp(ctx, rsvp_type, party_info)

    async def _rsvp(self, ctx, rsvp_type, party_info):
        if not ctx.prefix:
            prefix = self.bot._get_prefix(self.bot, ctx.message)
            ctx.prefix = prefix[-1]
        if not ctx.invoked_with:
            ctx.invoked_with = self.bot.get_command(rsvp_type)
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        report_dict = await utils.get_report_dict(self.bot, channel)
        trainer_dict = self.bot.guild_dict[guild.id][report_dict][channel.id]['trainer_dict']
        entered_interest = trainer_dict.get(author.id, {}).get('interest', [])
        pokemon = self.bot.guild_dict[guild.id][report_dict][channel.id].get('pkmn_obj', None)
        meetup = self.bot.guild_dict[guild.id][report_dict][channel.id].get('meetup', None)
        lobby = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].get('lobby', None)
        egg_level = self.bot.guild_dict[guild.id][report_dict][channel.id]['egg_level']
        list_emoji = self.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f')
        raidtype = _("event") if self.bot.guild_dict[channel.guild.id][report_dict][channel.id].get('meetup', False) else _("raid")
        boss_list = []
        if not meetup:
            if not pokemon:
                for boss in self.bot.raid_dict[str(egg_level)]:
                    if isinstance(boss, pkmn_class.Pokemon):
                        boss_list.append(str(boss).lower())
            else:
                pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, pokemon)
                boss_list.append(str(pokemon).lower())
        pkmn_match = None
        if party_info:
            pkmn_split = party_info.split(',')
            pkmn_split = [x.strip() for x in pkmn_split]
            party_list = []
            first_split = pkmn_split[0].split()
            for item in first_split:
                party_search = re.search(r'\d+[vimrybgu]*', item)
                if party_search:
                    party_list.append(item)
                    pkmn_split[0] = pkmn_split[0].replace(item, '').strip()
            if "all" in party_info.lower():
                pkmn_split = boss_list
                pkmn_match = True
            party_info = (' ').join(party_list)
            if not pkmn_match:
                for index, item in enumerate(pkmn_split):
                    pkmn_match = await pkmn_class.Pokemon.async_get_pokemon(self.bot, item)
                    if pkmn_match:
                        if str(pkmn_match).lower() in boss_list:
                            pkmn_split[index] = str(pkmn_match).lower()
                        elif pkmn_match.id in self.bot.raid_dict[str(egg_level)]:
                            for boss in self.bot.raid_dict[str(egg_level)]:
                                if isinstance(boss, pkmn_class.Pokemon) and boss.id == pkmn_match.id:
                                    pkmn_split[index] = str(boss).lower()
                                    break
                        else:
                            pkmn_split[index] = ""
                    else:
                        pkmn_split[index] = ""
            pkmn_split = [x for x in pkmn_split if x]
            if pkmn_match and self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['type'] == 'egg':
                entered_interest = []
                for pkmn in pkmn_split:
                    if pkmn not in entered_interest:
                        entered_interest.append(pkmn)
            elif not pkmn_match and self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['type'] == 'egg':
                entered_interest = boss_list
                interest = trainer_dict.get(ctx.author.id, {}).get('interest', [])
                if interest:
                    entered_interest = interest
        else:
            if ctx.author.id in trainer_dict:
                bluecount = str(trainer_dict[ctx.author.id]['party']['mystic']) + 'm '
                redcount = str(trainer_dict[ctx.author.id]['party']['valor']) + 'v '
                yellowcount = str(trainer_dict[ctx.author.id]['party']['instinct']) + 'i '
                unknowncount = str(trainer_dict[ctx.author.id]['party']['unknown']) + 'u '
                party_info = ((((str(trainer_dict[ctx.author.id]['count']) + ' ') + bluecount) + redcount) + yellowcount) + unknowncount
            else:
                party_info = '1'
            if self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['type'] == 'egg':
                entered_interest = boss_list
                interest = trainer_dict.get(ctx.author.id, {}).get('interest', [])
                if interest:
                    entered_interest = interest
        if party_info and party_info.split()[0].isdigit():
            total = int(party_info.split()[0])
        elif (ctx.author.id in trainer_dict) and (sum(trainer_dict[ctx.author.id]['status'].values()) > 0):
            total = trainer_dict[ctx.author.id]['count']
        elif party_info:
            total = re.sub('[^0-9 ]', '', party_info)
            total = sum([int(x) for x in total.split()])
        else:
            total = 1
        result = await self._party_status(ctx, total, party_info)
        if not isinstance(result, list):
            return
        trainer_dict = self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['trainer_dict'].get(author.id, {})
        if trainer_dict and trainer_dict.setdefault('status', {}).get(rsvp_type, None) and result[1] == trainer_dict.setdefault('party', {}) and not trainer_dict['status'].get('lobby'):
            await ctx.send(f"{ctx.author.display_name}, your status is already set to **{rsvp_type}**. If you're trying to add more trainers use **{ctx.prefix}{ctx.invoked_with} [total count] [team counts]** like `{ctx.prefix}{ctx.invoked_with} 3 1m 2v`.", delete_after=60)
        count = result[0]
        party = result[1]
        blue_count = 0
        red_count = 0
        yellow_count = 0
        grey_count = 0
        interest_str = ""
        if (not party):
            for role in author.roles:
                if role.id == self.bot.guild_dict[guild.id]['configure_dict'].get('team', {}).get('team_roles', {}).get('mystic', 0):
                    blue_count = count
                    break
                elif role.id == self.bot.guild_dict[guild.id]['configure_dict'].get('team', {}).get('team_roles', {}).get('valor', 0):
                    red_count = count
                    break
                elif role.id == self.bot.guild_dict[guild.id]['configure_dict'].get('team', {}).get('team_roles', {}).get('instinct', 0):
                    yellow_count = count
                    break
            else:
                grey_count = count
            party = {'mystic':blue_count, 'valor':red_count, 'instinct':yellow_count, 'unknown':grey_count}
        if entered_interest and len(entered_interest) != len(boss_list):
            if rsvp_type == "maybe":
                interest_str = f" in {(', ').join([x.title() for x in entered_interest])}"
            elif rsvp_type == "coming" or rsvp_type == "here":
                interest_str = f" for {(', ').join([x.title() for x in entered_interest])}"
        if count == 1:
            team_emoji = max(party, key=lambda key: party[key])
            if team_emoji == "unknown":
                team_emoji = utils.parse_emoji(channel.guild, self.bot.config.unknown)
            else:
                team_emoji = utils.parse_emoji(channel.guild, self.bot.config.team_dict[team_emoji])
            if rsvp_type == "maybe":
                rsvp_message = await channel.send(_('Meowth! {member} is interested{interest_str}! {emoji}: 1').format(member=author.mention, interest_str=interest_str, emoji=team_emoji))
            elif rsvp_type == "coming":
                rsvp_message = await channel.send(_('Meowth! {member} is on the way{interest_str}! {emoji}: 1').format(member=author.mention, interest_str=interest_str, emoji=team_emoji))
            elif rsvp_type == "here":
                rsvp_message = await channel.send(_('Meowth! {member} is at the {raidtype}{interest_str}! {emoji}: 1').format(member=author.mention, emoji=team_emoji, interest_str=interest_str, raidtype=raidtype))
            elif rsvp_type == "lobby":
                rsvp_message = await channel.send(_('Meowth! {member} is entering the lobby! {emoji}: 1').format(member=author.mention, emoji=team_emoji))
        else:
            blue_emoji = utils.parse_emoji(channel.guild, self.bot.config.team_dict['mystic'])
            red_emoji = utils.parse_emoji(channel.guild, self.bot.config.team_dict['valor'])
            yellow_emoji = utils.parse_emoji(channel.guild, self.bot.config.team_dict['instinct'])
            grey_emoji = utils.parse_emoji(channel.guild, self.bot.config.unknown)
            if rsvp_type == "maybe":
                msg = f"Meowth! {author.mention} is interested{interest_str} with a total of **{count}** trainers! "
            elif rsvp_type == "coming":
                msg = f"Meowth! {author.mention} is on the way with a total of **{count}** trainers{interest_str}! "
            elif rsvp_type == "here":
                msg = f"Meowth! {author.mention} is at the {raidtype} with a total of **{count}** trainers{interest_str}! "
            elif rsvp_type == "lobby":
                msg = f"Meowth! {author.mention} is entering the lobby with a total of {count} trainers! "
            if party['mystic']:
                msg += f"{blue_emoji}: {party['mystic']} | "
            if party['valor']:
                msg += f"{red_emoji}: {party['valor']} | "
            if party['instinct']:
                msg += f"{yellow_emoji}: {party['instinct']} | "
            if party['unknown']:
                msg += f"{grey_emoji}: {party['unknown']} | "
            rsvp_message = await channel.send(msg[:-3])
        await utils.add_reaction(rsvp_message, list_emoji)
        if lobby and rsvp_type == "here":
            if author.id in lobby.get('starting_dict', {}).keys():
                try:
                    del self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['lobby']['starting_dict'][author.id]
                except (IndexError, KeyError):
                    pass
            else:
                await channel.send(f"{author.mention}, there is a group already in the lobby! Use **!lobby** to join them or **!backout** to request a backout! Otherwise, you may have to wait for the next group!")
        if rsvp_type == "maybe":
            trainer_dict['status'] = {'maybe':count, 'coming':0, 'here':0, 'lobby':0}
        elif rsvp_type == "coming":
            trainer_dict['status'] = {'maybe':0, 'coming':count, 'here':0, 'lobby':0}
        elif rsvp_type == "here":
            trainer_dict['status'] = {'maybe':0, 'coming':0, 'here':count, 'lobby':0}
        elif rsvp_type == "lobby":
            trainer_dict['status'] = {'maybe':0, 'coming':0, 'here':0, 'lobby':count}
            self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['lobby']['starting_dict'][author.id] = {"count":count, "status":trainer_dict['status'], "party":party}
        if entered_interest:
            trainer_dict['interest'] = entered_interest
        trainer_dict['count'] = count
        trainer_dict['party'] = party
        self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['trainer_dict'][author.id] = trainer_dict
        await self._edit_party(channel, author)
        rsvp_emoji = self.bot.custom_emoji.get('rsvp_emoji', u"\U0001f4ac")
        if rsvp_emoji not in channel.name:
            raid_channel_name = await self.edit_channel_name(channel)
            await channel.edit(name=raid_channel_name)
        for trainer in self.bot.guild_dict[guild.id][report_dict][channel.id].get('alert_list', []):
            member = guild.get_member(trainer)
            if author == member:
                continue
            alert_emoji = self.bot.custom_emoji.get('alert_emoji', u'\U0001f514')
            await member.send(f"{alert_emoji} - {author.display_name} has RSVP'd as **{rsvp_type}** in {channel.mention}.", delete_after=3600)

    @commands.command(aliases=['x'])
    @checks.rsvpchannel()
    async def cancel(self, ctx):
        """Indicate you are no longer interested in a raid.

        Usage: !cancel
        Works only in raid channels. Removes you and your party
        from the list of trainers who are "otw" or "here"."""
        await self._cancel(ctx)

    async def _cancel(self, ctx):
        guild = ctx.guild
        channel = ctx.channel
        author = ctx.author
        report_dict = await utils.get_report_dict(self.bot, channel)
        raidtype = _("event") if self.bot.guild_dict[guild.id][report_dict][channel.id].get('meetup', False) else _("raid")
        try:
            t_dict = self.bot.guild_dict[guild.id][report_dict][channel.id]['trainer_dict'][author.id]
        except KeyError:
            return await channel.send(_('Meowth! {member} has no status to cancel!').format(member=author.mention), delete_after=10)
        if t_dict['status'] == {'maybe':0, 'coming':0, 'here':0, 'lobby':0}:
            await channel.send(_('Meowth! {member} has no status to cancel!').format(member=author.mention), delete_after=10)
        if t_dict['status']['maybe']:
            if t_dict['count'] == 1:
                await channel.send(_('Meowth! {member} is no longer interested!').format(member=author.mention))
            else:
                await channel.send(_('Meowth! {member} and their total of {trainer_count} trainers are no longer interested!').format(member=author.mention, trainer_count=t_dict['count']))
        if t_dict['status']['here']:
            if t_dict['count'] == 1:
                await channel.send(_('Meowth! {member} has left the {raidtype}!').format(member=author.mention, raidtype=raidtype))
            else:
                await channel.send(_('Meowth! {member} and their total of {trainer_count} trainers have left the {raidtype}!').format(member=author.mention, trainer_count=t_dict['count'], raidtype=raidtype))
        if t_dict['status']['coming']:
            if t_dict['count'] == 1:
                await channel.send(_('Meowth! {member} is no longer on their way!').format(member=author.mention))
            else:
                await channel.send(_('Meowth! {member} and their total of {trainer_count} trainers are no longer on their way!').format(member=author.mention, trainer_count=t_dict['count']))
        if t_dict['status']['lobby']:
            if t_dict['count'] == 1:
                await channel.send(_('Meowth! {member} has backed out of the lobby!').format(member=author.mention))
            else:
                await channel.send(_('Meowth! {member} and their total of {trainer_count} trainers have backed out of the lobby!').format(member=author.mention, trainer_count=t_dict['count']))
        t_dict['status'] = {'maybe':0, 'coming':0, 'here':0, 'lobby':0}
        t_dict['party'] = {'mystic':0, 'valor':0, 'instinct':0, 'unknown':0}
        t_dict['interest'] = []
        t_dict['count'] = 1
        await self._edit_party(channel, author)
        total_count = 0
        for trainer in list(self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['trainer_dict']):
            total_count += sum(self.bot.guild_dict[channel.guild.id][report_dict][channel.id]['trainer_dict'][trainer]['status'].values())
        if total_count == 0:
            raid_channel_name = await self.edit_channel_name(channel)
            await channel.edit(name=raid_channel_name)
        # if total_count%3 == 0:
        #     await ctx.invoke(self.bot.get_command("list"))

    @tasks.loop(seconds=21600)
    async def lobby_cleanup(self, loop=True):
        for guild in self.bot.guilds:
            if guild.id not in list(self.bot.guild_dict.keys()):
                continue
            for report_dict in self.bot.channel_report_dicts:
                try:
                    guild_raids = copy.deepcopy(self.bot.guild_dict[guild.id][report_dict])
                    for raid in guild_raids:
                        lobby = guild_raids[raid].get("lobby", False)
                        battling = guild_raids[raid].get("battling", False)
                        if not lobby and not battling:
                            continue
                        first_message = guild_raids[raid].get("raid_message", False)
                        raid_channel = self.bot.get_channel(raid)
                        try:
                            raid_message = await raid_channel.fetch_message(first_message)
                        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                            continue
                        ctx = await self.bot.get_context(raid_message)
                        self.bot.loop.create_task(self.lobby_countdown(ctx))
                except Exception as e:
                    print(traceback.format_exc())
        if not loop:
            return

    @lobby_cleanup.before_loop
    async def before_lobby_cleanup(self):
        await self.bot.wait_until_ready()

    async def lobby_countdown(self, ctx):
        try:
            report_dict = await utils.get_report_dict(ctx.bot, ctx.channel)
            if 'raidchannel' not in str(report_dict):
                return
            def check_battling():
                for lobby in self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].get('battling', []):
                    if lobby and time.time() >= lobby['exp']:
                        try:
                            self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['battling'].remove(lobby)
                            self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['completed'].append(lobby)
                        except:
                            pass
            while True:
                check_battling()
                start_lobby = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].setdefault('lobby', {})
                battling = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].setdefault('battling', [])
                report_channel = self.bot.get_channel(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].get('report_channel', None))
                if not start_lobby and not battling:
                    return
                if report_channel and checks.check_tutorialchannel(ctx):
                    return
                completed = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].setdefault('completed', [])
                egg_level = utils.get_level(self.bot, self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['pkmn_obj'])
                start_exp = start_lobby.get('exp', False)
                start_team = start_lobby.get('team', False)
                team_names = ["mystic", "valor", "instinct", "unknown"]
                trainer_dict = copy.deepcopy(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['trainer_dict'])
                if time.time() < start_exp:
                    sleep_time = start_exp - time.time()
                    await asyncio.sleep(int(sleep_time))
                    continue
                elif time.time() >= start_exp:
                    ctx_lobbycount = 0
                    trainer_delete_list = []
                    for trainer in trainer_dict:
                        if trainer_dict[trainer]['status']['lobby']:
                            ctx_lobbycount += trainer_dict[trainer]['status']['lobby']
                            trainer_delete_list.append(trainer)
                    for trainer in trainer_delete_list:
                        if start_team in team_names:
                            herecount = start_lobby['starting_dict'].get('herecount', 0)
                            teamcount = start_lobby['starting_dict'].get('teamcount', 0)
                            lobbycount = start_lobby['starting_dict'].get('lobbycount', 0)
                            trainer_dict[trainer]['status'] = {'maybe':0, 'coming':0, 'here':herecount - teamcount, 'lobby': lobbycount}
                            trainer_dict[trainer]['party'][start_team] = 0
                            trainer_dict[trainer]['count'] = trainer_dict[trainer]['count'] - teamcount
                        else:
                            del trainer_dict[trainer]
                    if egg_level == "EX" or egg_level == "5":
                        battle_time = 300
                    else:
                        battle_time = 180
                    start_lobby['exp'] = start_exp + battle_time
                    if trainer_delete_list:
                        if start_lobby not in battling:
                            self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['battling'].append(start_lobby)
                        if ctx_lobbycount > 0:
                            battling_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/unicode_collision.png?cache=1")
                            battling_embed.add_field(name=f"**Lobby Battling**", value=f"Meowth! The group of {str(ctx_lobbycount)} in the lobby has entered the raid! Wish them luck!")
                            await ctx.channel.send(embed=battling_embed, delete_after=battle_time)
                    del self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['lobby']
                    self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['trainer_dict'] = trainer_dict
                    raid_channel_name = await self.edit_channel_name(ctx.channel)
                    await ctx.channel.edit(name=raid_channel_name)
                    await self._edit_party(ctx.channel, ctx.author)
                    check_battling()
                    await asyncio.sleep(battle_time)
                    trainer_list = [ctx.guild.get_member(x) for x in trainer_delete_list]
                    battling_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/unicode_whitecheck.png?cache=1")
                    battling_embed.add_field(name=f"**Battle Completed**", value=f"Meowth! The group of {', '.join([x.mention for x in trainer_list])} has finished the raid! Use **{ctx.prefix}list groups** to see all groups.")
                    await ctx.channel.send(embed=battling_embed)
                    try:
                        self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['battling'].remove(start_lobby)
                        self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['completed'].append(start_lobby)
                    except:
                        pass
                    raid_channel_name = await self.edit_channel_name(ctx.channel)
                    await ctx.channel.edit(name=raid_channel_name)
                    break
            check_battling()
        except:
            return

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @checks.rsvpchannel()
    async def starting(self, ctx, team: str = ''):
        """Signal that a raid is starting.

        Usage: !starting [team]
        Works only in rsvp channels. Sends a message and clears the waiting list. Users who are waiting
        for a second group must reannounce with the :here: emoji or !here."""
        starting_dict = {}
        ctx_startinglist = []
        id_startinglist = []
        cancel_reaction = self.bot.custom_emoji.get('raid_cancel', u'\U0000274C')
        report_dict = await utils.get_report_dict(self.bot, ctx.channel)
        team_list = []
        team_names = ["mystic", "valor", "instinct", "unknown"]
        team = team if team and team.lower() in team_names else "all"
        trainer_dict = copy.deepcopy(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['trainer_dict'])
        starting_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/unicode_play.png?cache=1")
        if checks.check_meetupchannel(ctx):
            starting_embed.add_field(name=f"**Not Supported**", value=f"Meowth! Meetup channels do not support **{ctx.prefix}starting**")
            return await ctx.channel.send(embed=starting_embed, delete_after=10)
        if checks.check_trainchannel(ctx):
            if not self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].get('meetup', {}).get('raid', False):
                return await utils.safe_delete(ctx.message)
            all_trainers = []
            for trainer in trainer_dict:
                user = ctx.guild.get_member(trainer)
                if not user:
                    continue
                if sum(trainer_dict[trainer]['status'].values()) == 0:
                    continue
                all_trainers.append(user)
            if all_trainers:
                starting_str = f"Starting - Trainers {(', ').join([x.mention for x in all_trainers])}"
                starting_embed.add_field(name=f"**Starting**", value=f"Meowth! The group that was waiting is starting at the current train location! If you are with them you should start as well. If you are not with them wait for next train location to be announced if it has not already. If you are no longer following the train, reply with **{ctx.prefix}x** or react with {cancel_reaction} above to leave the train.")
            else:
                starting_str = ""
                starting_embed.add_field(name=f"**Starting Error**", value=f"Meowth! How can you start when there's no one waiting at this raid!?")
            return await ctx.channel.send(starting_str, embed=starting_embed)
        if self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].get('type', None) == 'egg' and not checks.check_meetupchannel(ctx):
            starting_embed.add_field(name=f"**Starting Error**", value=f"Meowth! How can you start when the egg hasn't hatched!?")
            return await ctx.channel.send(embed=starting_embed, delete_after=10)
        if self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].get('lobby', False):
            starting_embed.add_field(name=f"**Starting Error**", value=f"Meowth! Please wait for the group in the lobby to enter the raid.")
            await ctx.channel.send(embed=starting_embed, delete_after=10)
            self.bot.loop.create_task(self.lobby_countdown(ctx))
            return
        for trainer in trainer_dict:
            ctx.count = trainer_dict[trainer].get('count', 1)
            user = ctx.guild.get_member(trainer)
            if not user:
                continue
            herecount = trainer_dict[trainer]['status']['here']
            lobbycount = trainer_dict[trainer]['status']['lobby']
            teamcount = herecount
            if team in team_names:
                if trainer_dict[trainer]['party'][team]:
                    team_list.append(user.id)
                teamcount = trainer_dict[trainer]['party'][team]
                if trainer_dict[trainer]['status']['here'] and (user.id in team_list):
                    trainer_dict[trainer]['status'] = {'maybe':0, 'coming':0, 'here':herecount - teamcount, 'lobby':lobbycount + teamcount}
                    ctx_startinglist.append(user)
                    id_startinglist.append(trainer)
            else:
                if trainer_dict[trainer]['status']['here'] and (user.id in team_list or team == "all"):
                    trainer_dict[trainer]['status'] = {'maybe':0, 'coming':0, 'here':0, 'lobby':ctx.count}
                    ctx_startinglist.append(user)
                    id_startinglist.append(trainer)
            if trainer_dict[trainer]['status']['lobby']:
                starting_dict[trainer] = {"count":trainer_dict[trainer]['count'], "status":trainer_dict[trainer]['status'], "party":trainer_dict[trainer]['party'], "herecount":herecount, "teamcount":teamcount, "lobbycount":lobbycount}
        if len(ctx_startinglist) == 0:
            starting_embed.add_field(name=f"", value=f"Meowth! How can you start when there's no one waiting at this raid!?")
            return await ctx.channel.send(embed=starting_embed, delete_after=10)
        if team in team_names:
            starting_embed.add_field(name=f"**Confirm Starting**", value=f"Are you sure you would like to start this raid? React to this message to confirm or cancel the start of the raid.")
            question = await ctx.channel.send(f"Confirm Starting - Trainers {', '.join([x.mention for x in ctx_startinglist])}", embed=starting_embed)
        else:
            starting_embed.add_field(name=f"**Confirm Starting**", value=f"Are you sure you would like to start this raid? You can also use **{ctx.prefix}starting [team]** to start that team only. React to this message to confirm or cancel the start of the raid.")
            question = await ctx.channel.send(f"Confirm Starting - Trainers {', '.join([x.mention for x in ctx_startinglist])}", embed=starting_embed)
        starting_embed.clear_fields()
        try:
            timeout = False
            res, reactuser = await utils.ask(self.bot, question, id_startinglist)
        except TypeError:
            timeout = True
        if timeout:
            starting_embed.add_field(name=f"**Starting Error**", value=f"Meowth! The **{ctx.prefix}starting** command was not confirmed. I\'m not sure if the group started.")
            await ctx.channel.send(embed=starting_embed)
        if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', u'\U0000274e'):
            return await utils.safe_delete(question)
        elif res.emoji == self.bot.custom_emoji.get('answer_yes', u'\U00002705'):
            await utils.safe_delete(question)
            self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['trainer_dict'] = trainer_dict
            starttime = self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].get('starttime', None)
            if starttime:
                timestr = _(' to start at **{}** ').format(starttime.strftime(_('%I:%M %p (%H:%M)')))
                self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['starttime'] = None
            else:
                timestr = ' '
            self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['lobby'] = {"exp":time.time() + 120, "team":team, "starting_dict":starting_dict}
            here_emoji = utils.parse_emoji(ctx.guild, self.bot.config.here_id)
            starting_str = f"Meowth! The group that was waiting{timestr}is starting the raid! If you are waiting for another group, reply with {here_emoji} or **{ctx.prefix}here**. If you need to ask for the group to back out of their lobby, use **{ctx.prefix}backout**. If you aren't listed, join the current lobby using **{ctx.prefix}lobby**."
            if starttime:
                starting_str += f"\n\nThe start time has also been cleared, new groups can set a new start time wtih **{ctx.prefix}starttime [HH:MM AM/PM]** (You can also omit AM/PM and use 24-hour time!)."
            starting_embed.add_field(name=f"**Starting**", value=f"{starting_str}")
            await ctx.channel.send(f"Starting - Trainers {', '.join([x.mention for x in ctx_startinglist])}", embed=starting_embed, delete_after=500)
            raid_channel_name = await self.edit_channel_name(ctx.channel)
            await ctx.channel.edit(name=raid_channel_name)
            self.bot.loop.create_task(self.lobby_countdown(ctx))
            if starttime:
                report_channel = self.bot.get_channel(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['report_channel'])
                raidmsg = await ctx.channel.fetch_message(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['raid_message'])
                reportmsg = await report_channel.fetch_message(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['raid_report'])
                embed = raidmsg.embeds[0]
                index = 0
                for field in embed.fields:
                    if _("**Next Group:**") in field.name:
                        embed.set_field_at(index, name=_("**Next Group:**"), value=_("Set with **!starttime**"), inline=field.inline)
                        break
                    else:
                        index += 1
                try:
                    await raidmsg.edit(content=raidmsg.content, embed=embed)
                except:
                    pass
                try:
                    await reportmsg.edit(content=reportmsg.content, embed=embed)
                except:
                    pass
                try:
                    timerset_embed = discord.Embed(colour=channel.guild.me.colour).set_author(name="Channel Timer")
                    timerset_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_date.png?cache=1")
                    timerstr = await self.print_raid_timer(ctx.channel)
                    timerset_embed.add_field(name=f"**Channel Timer**", value=f"{timerstr}")
                    timerset_msg = await ctx.channel.fetch_message(self.bot.guild_dict[guild.id][report_dict][ctx.channel.id]['timerset_msg'])
                    await timerset_msg.edit(content=None, embed=timerset_embed)
                except:
                    pass

    @commands.command()
    @checks.activeraidchannel()
    async def backout(self, ctx):
        """Request players in lobby to backout

        Usage: !backout
        Will alert all trainers in the lobby that a backout is requested."""
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = channel.guild
        report_dict = await utils.get_report_dict(ctx.bot, ctx.channel)
        trainer_dict = self.bot.guild_dict[guild.id][report_dict][channel.id]['trainer_dict']
        battling = self.bot.guild_dict[guild.id][report_dict][channel.id].get('battling', [])
        battle_lobby = {}
        lobby_list = []
        if battling:
            for lobby in battling:
                if ctx.author.id in lobby['starting_dict'].keys():
                    battle_lobby = lobby
                    self.bot.guild_dict[guild.id][report_dict][channel.id]['battling'].remove(lobby)
                    break
        if battle_lobby:
            for trainer in battle_lobby['starting_dict'].keys():
                user = guild.get_member(trainer)
                if not user:
                    continue
                if battle_lobby['starting_dict'][trainer]['status'] == {'maybe':0, 'coming':0, 'here':0, 'lobby':0}:
                    continue
                lobby_list.append(user)
                count = battle_lobby['starting_dict'][trainer]['status']['lobby']
                battle_lobby['starting_dict'][trainer]['status'] = {'maybe':0, 'coming':count, 'here':0, 'lobby':0}
                if user == author:
                    continue
                await user.send(f"Backout - Meowth! {author.display_name} has requested a backout in {channel.mention}. Please check the channel and back out of the raid if required.", delete_after=300)
            self.bot.guild_dict[guild.id][report_dict][channel.id]['trainer_dict'] = {**trainer_dict, **battle_lobby['starting_dict']}
            await channel.send(_('Backout - Meowth! {author} has requested that the group consisting of {lobby_list} and the people with them to back out of the battle! Please confirm that you have backed out with **!here**. The lobby will have to be started again using **!starting**.').format(author=author.mention, lobby_list=', '.join([x.mention for x in lobby_list])))
            raid_channel_name = await self.edit_channel_name(channel)
            await channel.edit(name=raid_channel_name)
        elif (author.id in trainer_dict) and (trainer_dict[author.id]['status']['lobby']):
            count = trainer_dict[author.id]['count']
            trainer_dict[author.id]['status'] = {'maybe':0, 'coming':0, 'here':count, 'lobby':0}
            for trainer in trainer_dict:
                count = trainer_dict[trainer]['count']
                if trainer_dict[trainer]['status']['lobby']:
                    user = guild.get_member(trainer)
                    if not user:
                        continue
                    lobby_list.append(user)
                    trainer_dict[trainer]['status'] = {'maybe':0, 'coming':0, 'here':count, 'lobby':0}
                    if user == author:
                        continue
                    await user.send(f"Backout - Meowth! {author.display_name} has requested a backout in {channel.mention}. Please check the channel and back out of the raid if required.", delete_after=300)
            if (not lobby_list):
                await channel.send(_("Meowth! There's no one else in the lobby for this raid!"), delete_after=10)
                try:
                    del self.bot.guild_dict[guild.id][report_dict][channel.id]['lobby']
                except KeyError:
                    pass
                raid_channel_name = await self.edit_channel_name(channel)
                await channel.edit(name=raid_channel_name)
                return
            await channel.send(_('Backout - Meowth! {author} has indicated that the group consisting of {lobby_list} and the people with them has backed out of the lobby! If this is inaccurate, please use **!lobby** or **!cancel** to help me keep my lists accurate!').format(author=author.mention, lobby_list=', '.join([x.mention for x in lobby_list])))
            try:
                del self.bot.guild_dict[guild.id][report_dict][channel.id]['lobby']
            except KeyError:
                pass
            raid_channel_name = await self.edit_channel_name(channel)
            await channel.edit(name=raid_channel_name)
        else:
            trainer_list = []
            for trainer in trainer_dict:
                if trainer_dict[trainer]['status']['lobby']:
                    user = guild.get_member(trainer)
                    if not user:
                        continue
                    lobby_list.append(user)
                    trainer_list.append(trainer)
                    if user == author:
                        continue
                    await user.send(f"Backout - Meowth! {author.display_name} has requested a backout in {channel.mention}. Please check the channel and back out of the raid if required.", delete_after=300)
            if (not lobby_list):
                await channel.send(_("Meowth! There's no one in the lobby for this raid!"), delete_after=10)
                return

            backoutmsg = await channel.send(_('Backout - Meowth! {author} has requested a backout! If one of the following trainers reacts with the check mark, I will assume the group is backing out of the raid lobby as requested! {lobby_list}').format(author=author.mention, lobby_list=', '.join([x.mention for x in lobby_list])))
            try:
                timeout = False
                res, reactuser = await utils.ask(self.bot, backoutmsg, trainer_list, react_list=[self.bot.custom_emoji.get('answer_yes', u'\U00002705')])
            except TypeError:
                timeout = True
            if not timeout and res.emoji == self.bot.custom_emoji.get('answer_yes', u'\U00002705'):
                for trainer in trainer_list:
                    count = trainer_dict[trainer]['count']
                    if trainer in trainer_dict:
                        trainer_dict[trainer]['status'] = {'maybe':0, 'coming':0, 'here':count, 'lobby':0}
                await channel.send(_('Meowth! {user} confirmed the group is backing out!').format(user=reactuser.mention))
                try:
                    del self.bot.guild_dict[guild.id][report_dict][channel.id]['lobby']
                except KeyError:
                    pass
                raid_channel_name = await self.edit_channel_name(channel)
                await channel.edit(name=raid_channel_name)
            else:
                return

def setup(bot):
    bot.add_cog(Raid(bot))

def teardown(bot):
    bot.remove_cog(Raid)
