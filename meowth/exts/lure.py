import asyncio
import copy
import re
import time
import datetime
import dateparser
import textwrap
import logging
import string
import traceback

import discord
from discord.ext import commands, tasks

from meowth import checks
from meowth.exts import pokemon as pkmn_class
from meowth.exts import utilities as utils

logger = logging.getLogger("meowth")

class Lure(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lure_cleanup.start()

    def cog_unload(self):
        self.lure_cleanup.cancel()

    @tasks.loop(seconds=0)
    async def lure_cleanup(self, loop=True):
        logger.info('------ BEGIN ------')
        expire_list = []
        count = 0
        for guild in list(self.bot.guilds):
            try:
                lure_dict = self.bot.guild_dict[guild.id].setdefault('lure_dict', {})
                for reportid in list(lure_dict.keys()):
                    if lure_dict.get(reportid, {}).get('exp', 0) <= time.time():
                        report_channel = self.bot.get_channel(lure_dict.get(reportid, {}).get('report_channel'))
                        if report_channel:
                            try:
                                report_message = await report_channel.fetch_message(reportid)
                                self.bot.loop.create_task(self.expire_lure(report_message))
                                count += 1
                                continue
                            except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                                pass
                        try:
                            self.bot.loop.create_task(utils.expire_dm_reports(self.bot, lure_dict.get(reportid, {}).get('dm_dict', {})))
                            del self.bot.guild_dict[guild.id]['lure_dict'][reportid]
                            count += 1
                            continue
                        except KeyError:
                            continue
                    to_expire = lure_dict.get(reportid, {}).get('exp', 0) - time.time()
                    if to_expire > 0:
                        expire_list.append(to_expire)
            except Exception as e:
                print(traceback.format_exc())
        # save server_dict changes after cleanup
        logger.info('SAVING CHANGES')
        try:
            await self.bot.save
        except Exception as err:
            logger.info('SAVING FAILED' + err)
            pass
        if not expire_list:
            expire_list = [600]
        logger.info(f"------ END - {count} Lures Cleaned - Waiting {min(expire_list)} seconds. ------")
        if not loop:
            return
        self.lure_cleanup.change_interval(seconds=min(expire_list))

    @lure_cleanup.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        channel = self.bot.get_channel(payload.channel_id)
        guild = getattr(channel, "guild", None)
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
        can_manage = channel.permissions_for(user).manage_messages
        if not can_manage and user.id in self.bot.config.managers:
            can_manage = True
        try:
            lure_dict = self.bot.guild_dict[guild.id]['lure_dict']
        except KeyError:
            lure_dict = {}
        if message.id in lure_dict:
            lure_dict =  self.bot.guild_dict[guild.id]['lure_dict'][message.id]
            if str(payload.emoji) == self.bot.custom_emoji.get('wild_catch', '\U0001f1f7'):
                if user.id not in lure_dict.get('caught_by', []):
                    if user.id != lure_dict['report_author']:
                        lure_dict.setdefault('caught_by', []).append(user.id)
            elif str(payload.emoji) == self.bot.custom_emoji.get('lure_expire', '\U0001F4A8'):
                for reaction in message.reactions:
                    if reaction.emoji == self.bot.custom_emoji.get('lure_expire', '\U0001F4A8') and (reaction.count >= 3 or can_manage):
                        await self.expire_lure(message)
            elif str(payload.emoji) == self.bot.custom_emoji.get('lure_info', '\u2139'):
                if not ctx.prefix:
                    prefix = self.bot._get_prefix(self.bot, message)
                    ctx.prefix = prefix[-1]
                await message.remove_reaction(payload.emoji, user)
                ctx.author = user
                if user.id == lure_dict['report_author'] or can_manage:
                    await self.edit_lure_info(ctx, message)
            elif str(payload.emoji) == self.bot.custom_emoji.get('lure_report', '\U0001F4E2'):
                ctx = await self.bot.get_context(message)
                ctx.author, ctx.message.author = user, user
                await message.remove_reaction(payload.emoji, user)
                return await ctx.invoke(self.bot.get_command('lure'))
            elif str(payload.emoji) == self.bot.custom_emoji.get('list_emoji', '\U0001f5d2'):
                await asyncio.sleep(0.25)
                await message.remove_reaction(payload.emoji, self.bot.user)
                await asyncio.sleep(0.25)
                await message.remove_reaction(payload.emoji, user)
                await ctx.invoke(self.bot.get_command("list lures"))
                await asyncio.sleep(5)
                await utils.safe_reaction(message, payload.emoji)

    async def expire_lure(self, message):
        guild = message.channel.guild
        channel = message.channel
        lure_dict = copy.deepcopy(self.bot.guild_dict[guild.id]['lure_dict'])
        author = guild.get_member(lure_dict.get(message.id, {}).get('report_author'))
        await utils.safe_delete(message)
        try:
            user_message = await channel.fetch_message(lure_dict[message.id]['report_message'])
            await utils.safe_delete(user_message)
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, KeyError):
            pass
        await utils.expire_dm_reports(self.bot, lure_dict.get(message.id, {}).get('dm_dict', {}))
        lure_bonus = lure_dict[message.id].get('caught_by', [])
        if len(lure_bonus) >= 3 and author and not author.bot:
            lure_reports = self.bot.guild_dict[message.guild.id].setdefault('trainers', {}).setdefault(author.id, {}).setdefault('reports', {}).setdefault('lure', 0) + 1
            self.bot.guild_dict[message.guild.id]['trainers'][author.id]['reports']['lure'] = lure_reports
        try:
            del self.bot.guild_dict[guild.id]['lure_dict'][message.id]
        except KeyError:
            pass

    async def edit_lure_info(self, ctx, message):
        lure_dict = self.bot.guild_dict[ctx.guild.id]['lure_dict'].get(message.id, {})
        message = ctx.message
        channel = message.channel
        guild = message.guild
        author = guild.get_member(lure_dict.get('report_author', None))
        location = lure_dict.get('location', '')
        type_list = ["normal", "mossy", "magnetic", "glacial"]
        if not author:
            return
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[channel.guild.id]['configure_dict']['settings']['offset']))
        error = False
        success = []
        reply_msg = f"**type <lure type>** - Current: {lure_dict.get('type', 'X')}\n"
        lure_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey.png?cache=1')
        lure_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        while True:
            async with ctx.typing():
                lure_embed.add_field(name=_('**Edit Lure Info**'), value=f"Meowth! I'll help you edit information of the lure at **{location}**!\n\nI'll need to know what **values** you'd like to edit. Reply **cancel** to stop anytime or reply with a comma separated list of the following options `Ex: type mossy`:\n\n{reply_msg}", inline=False)
                value_wait = await channel.send(embed=lure_embed)
                def check(reply):
                    if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == ctx.author:
                        return True
                    else:
                        return False
                try:
                    value_msg = await self.bot.wait_for('message', timeout=60, check=check)
                except asyncio.TimeoutError:
                    value_msg = None
                await utils.safe_delete(value_wait)
                if not value_msg:
                    error = _("took too long to respond")
                    break
                else:
                    await utils.safe_delete(value_msg)
                if value_msg.clean_content.lower() == "cancel":
                    error = _("cancelled the report")
                    break
                else:
                    entered_values = value_msg.clean_content.lower().split(',')
                    entered_values = [x.strip() for x in entered_values]
                    for value in entered_values:
                        value_split = value.split()
                        if len(value_split) != 2:
                            error = _("entered something invalid")
                            continue
                        if "type" in value and "type" not in success:
                            if value_split[1] and value_split[1].lower() in type_list:
                                self.bot.guild_dict[ctx.guild.id]['lure_dict'][message.id]['type'] = value_split[1]
                                success.append("type")
                            else:
                                error = _('entered something invalid. Accepted types are Normal, Mossy, Glacial, Magnetic')
                        else:
                            error = _("entered something invalid")
                    break
        if success:
            await self.edit_lure_messages(ctx, message)
        else:
            error = _("didn't change anything")
        if error:
            lure_embed.clear_fields()
            lure_embed.add_field(name=_('**Lure Edit Cancelled**'), value=f"Meowth! Your edit has been cancelled because you **{error}**! Retry when you're ready.", inline=False)
            if success:
                lure_embed.set_field_at(0, name="**Lure Edit Error**", value=f"Meowth! Your **{(', ').join(success)}** edits were successful, but others were skipped because you **{error}**! Retry when you're ready.", inline=False)
            confirmation = await channel.send(embed=lure_embed, delete_after=10)

    async def edit_lure_messages(self, ctx, message):
        lure_dict = self.bot.guild_dict[ctx.guild.id]['lure_dict'].get(message.id, {})
        dm_dict = lure_dict.get('dm_dict', {})
        lure_type = lure_dict.get('type')
        level = lure_dict.get('level', None)
        lure_embed = message.embeds[0]
        location = lure_dict.get('location', None)
        author = ctx.guild.get_member(lure_dict.get('report_author', None))
        if author:
            ctx.author = author
        content = message.content
        lure_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey.png")
        lure_embed.set_author(name=f"Normal Lure Report", icon_url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey.png?cache=1")
        item = "lure module"
        if lure_type != "normal":
            lure_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey_{lure_type}.png")
            lure_embed.set_author(name=f"{lure_type.title()} Lure Report", icon_url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey_{lure_type}.png?cache=1")
            item = f"{lure_type} lure module"
        lure_embed.set_field_at(0, name=f"**Lure Type:**", value=item.title())
        try:
            await message.edit(content=content, embed=lure_embed)
        except:
            pass
        if isinstance(lure_embed.description, discord.embeds._EmptyEmbed):
            lure_embed.description = ""
        if "Jump to Message" not in lure_embed.description:
            lure_embed.description = lure_embed.description + f"\n**Report:** [Jump to Message]({message.jump_url})"
        index = 0
        for dm_user, dm_message in dm_dict.items():
            try:
                dm_user = self.bot.get_user(dm_user)
                dm_channel = dm_user.dm_channel
                if not dm_channel:
                    dm_channel = await dm_user.create_dm()
                if not dm_user or not dm_channel:
                    continue
                dm_message = await dm_channel.fetch_message(dm_message)
                content = dm_message.content
                await dm_message.edit(content=content, embed=lure_embed)
            except:
                pass
        ctx.lurereportmsg = message
        dm_dict = await self.send_dm_messages(ctx, location, item, content, copy.deepcopy(lure_embed), dm_dict)
        self.bot.guild_dict[ctx.guild.id]['lure_dict'][message.id]['dm_dict'] = dm_dict

    @commands.group(invoke_without_command=True, case_insensitive=True)
    @checks.allowlurereport()
    async def lure(self, ctx, lure_type=None, *, location:commands.clean_content(fix_channel_mentions=True)="", timer=""):
        """Report an ongoing lure.

        Usage: !lure [type] [pokestop] [minutes]
        Guided report available with just !lure"""
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset']))
        error = False
        first = True
        lure_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey.png?cache=1')
        lure_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        while True:
            async with ctx.typing():
                if lure_type and any([lure_type.lower() == "normal", lure_type.lower() == "mossy", lure_type.lower() == "glacial", lure_type.lower() == "magnetic"]) and location:
                    if location.split()[-1].isdigit():
                        timer = location.split()[-1]
                        location = location.replace(timer, '').strip()
                    if timer.isdigit() and int(timer) > 720:
                        timer = "720"
                    await self.send_lure(ctx, lure_type, location, timer)
                    return
                else:
                    def check(reply):
                        if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                            return True
                        else:
                            return False
                    if not lure_type or all([lure_type.lower() != "normal", lure_type.lower() != "mossy", lure_type.lower() != "glacial", lure_type.lower() != "magnetic"]):
                        lure_embed.add_field(name=_('**New Lure Report**'), value=_("Meowth! I will help you report a lure!\n\nFirst, I'll need to know what **type** the lure is. Reply with the **normal, mossy, magnetic, or glacial**. You can reply with **cancel** to stop anytime."), inline=False)
                        lure_type_wait = await channel.send(embed=lure_embed)
                        try:
                            lure_type_msg = await self.bot.wait_for('message', timeout=60, check=check)
                        except asyncio.TimeoutError:
                            lure_type_msg = None
                        await utils.safe_delete(lure_type_wait)
                        if not lure_type_msg:
                            error = _("took too long to respond")
                            break
                        else:
                            await utils.safe_delete(lure_type_msg)
                        if lure_type_msg.clean_content.lower() == "cancel":
                            error = _("cancelled the report")
                            break
                        elif not any([lure_type_msg.clean_content.lower() == "normal", lure_type_msg.clean_content.lower() == "mossy", lure_type_msg.clean_content.lower() == "magnetic", lure_type_msg.clean_content.lower() == "glacial"]):
                            error = _("entered an invalid type")
                            break
                        else:
                            lure_type = lure_type_msg.clean_content.lower()
                            first = False
                    if lure_type != "normal":
                        lure_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey_{lure_type}.png?cache=1")
                    lure_embed.clear_fields()
                    lure_embed.add_field(name="**New Lure Report**", value=f"{'Meowth! I will help you report a lure!' if first else ''}\n\n{'First, reply ' if first else 'Great! Now, reply '}with the **pokestop** that has the **{lure_type} lure**. You can reply with **cancel** to stop anytime.", inline=False)
                    location_wait = await channel.send(embed=lure_embed)
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
                    lure_embed.clear_fields()
                    lure_embed.add_field(name="**New Lure Report**", value=f"Fantastic! Now, reply with the **minutes remaining** before the **{lure_type} lure** at **{location}** ends. This is usually 30 minutes from when the lure started unless there is an event. If you don't know, reply with **N**. You can reply with **cancel** to stop anytime.", inline=False)
                    expire_wait = await channel.send(embed=lure_embed)
                    try:
                        expire_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        expire_msg = None
                    await utils.safe_delete(expire_wait)
                    if not expire_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(expire_msg)
                    if expire_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif expire_msg.clean_content.lower() == "n":
                        timer = ""
                    elif not expire_msg.clean_content.isdigit():
                        error = _("didn't enter a number")
                        break
                    elif int(expire_msg.clean_content) > 720:
                        timer = "720"
                    elif expire_msg:
                        timer = expire_msg.clean_content
                    lure_embed.remove_field(0)
                    break
        if not error:
            await self.send_lure(ctx, lure_type, location, timer)
        else:
            lure_embed.clear_fields()
            lure_embed.add_field(name=_('**Lure Report Cancelled**'), value=_("Meowth! Your report has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=lure_embed, delete_after=10)
            if not message.embeds:
                await utils.safe_delete(message)

    async def send_lure(self, ctx, lure_type, location, timer):
        dm_dict = {}
        expire_time = "30"
        if timer:
            expire_time = timer
        lure_dict = self.bot.guild_dict[ctx.guild.id].setdefault('lure_dict', {})
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.message.channel.guild.id]['configure_dict']['settings']['offset']))
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['offset'])
        end = now + datetime.timedelta(minutes=int(expire_time))
        catch_emoji = ctx.bot.custom_emoji.get('wild_catch', '\u26BE')
        info_emoji = ctx.bot.custom_emoji.get('lure_info', '\u2139')
        expire_emoji = self.bot.custom_emoji.get('lure_expire', '\U0001F4A8')
        report_emoji = self.bot.custom_emoji.get('lure_report', '\U0001F4E2')
        list_emoji = ctx.bot.custom_emoji.get('list_emoji', '\U0001f5d2')
        react_list = [catch_emoji, expire_emoji, info_emoji, report_emoji, list_emoji]
        lure_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey.png?cache=1')
        lure_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=ctx.author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=ctx.author.avatar_url_as(format=None, static_format='jpg', size=32))
        if timer:
            lure_msg = f"Meowth! {lure_type.title()} lure reported by {ctx.author.mention}! Details: {location}\n\nUse {catch_emoji} if visited, {info_emoji} to edit info, {report_emoji} to report new, or {list_emoji} to list all lures!"
        else:
            lure_msg = f"Meowth! {lure_type.title()} lure reported by {ctx.author.mention}! Details: {location}\n\nUse {catch_emoji} if visited, {expire_emoji} if expired, {info_emoji} to edit info, {report_emoji} to report new, or {list_emoji} to list all lures!!"
        lure_embed.title = _('Meowth! Click here for my directions to the lure!')
        lure_embed.description = f"Ask {ctx.author.name} if my directions aren't perfect!\n**Location:** {location}"
        loc_url = utils.create_gmaps_query(self.bot, location, ctx.channel, type="lure")
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        stop_info = ""
        if gym_matching_cog:
            stop_info, location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "lure")
            if stop_url:
                loc_url = stop_url
                lure_embed.description = stop_info
        if not location:
            return
        lure_embed.url = loc_url
        item = None
        lure_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey.png")
        lure_embed.set_author(name=f"Normal Lure Report", icon_url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey.png?cache=1")
        item = "lure module"
        if lure_type != "normal":
            lure_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey_{lure_type}.png")
            lure_embed.set_author(name=f"{lure_type.title()} Lure Report", icon_url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey_{lure_type}.png?cache=1")
            item = f"{lure_type} lure module"
        lure_embed.add_field(name=f"**Lure Type:**", value=item.title())
        lure_embed.add_field(name=f"**{'Expires' if timer else 'Expire Estimate'}:**", value=f"{expire_time} mins {end.strftime(_('(%I:%M %p)'))}")
        ctx.lurereportmsg = await ctx.channel.send(lure_msg, embed=lure_embed)
        self.bot.guild_dict[ctx.guild.id]['lure_dict'][ctx.lurereportmsg.id] = {
            'exp':time.time() + int(expire_time)*60,
            'report_message':ctx.message.id,
            'report_message':ctx.message.id,
            'report_channel':ctx.channel.id,
            'report_author':ctx.author.id,
            'report_guild':ctx.guild.id,
            'dm_dict':dm_dict,
            'location':location,
            'url':loc_url,
            'type':lure_type
        }
        if timer:
            react_list.remove(expire_emoji)
        for reaction in react_list:
            await asyncio.sleep(0.25)
            await utils.safe_reaction(ctx.lurereportmsg, reaction)
        if not ctx.message.author.bot:
            lure_reports = ctx.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('reports', {}).setdefault('lure', 0) + 1
            self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['reports']['lure'] = lure_reports
        dm_dict = await self.send_dm_messages(ctx, location, item, lure_msg, copy.deepcopy(lure_embed), dm_dict)
        self.bot.guild_dict[ctx.guild.id]['lure_dict'][ctx.lurereportmsg.id]['dm_dict'] = dm_dict

    async def send_dm_messages(self, ctx, location, item, content, embed, dm_dict):
        if embed:
            if isinstance(embed.description, discord.embeds._EmptyEmbed):
                embed.description = ""
            if "Jump to Message" not in embed.description:
                embed.description = embed.description + f"\n**Report:** [Jump to Message]({ctx.lurereportmsg.jump_url})"
            index = 0
            for field in embed.fields:
                if "reaction" in field.name.lower():
                    embed.remove_field(index)
                else:
                    index += 1
        content = content.splitlines()[0]
        content = content.replace(ctx.author.mention, f"{ctx.author.display_name} in {ctx.channel.mention}")
        for trainer in self.bot.guild_dict[ctx.guild.id].get('trainers', {}):
            user_stops = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('stops', [])
            stop_setting = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].get('alerts', {}).get('settings', {}).get('categories', {}).get('pokestop', {}).get('lure', True)
            user_items = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('items', [])
            item_setting = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].get('alerts', {}).get('settings', {}).get('categories', {}).get('item', {}).get('lure', True)

            if not any([user_stops, stop_setting, user_items, item_setting]):
                continue
            if not checks.dm_check(ctx, trainer) or trainer in dm_dict:
                continue
            send_lure = False
            if stop_setting and location.lower() in user_stops:
                send_lure = True
            if item_setting and item in user_items:
                send_lure = True
            if send_lure:
                try:
                    user = ctx.guild.get_member(trainer)
                    luredmmsg = await user.send(content, embed=embed)
                    dm_dict[user.id] = luredmmsg.id
                except:
                    continue
        return dm_dict

    @lure.command(aliases=['expire'])
    @checks.allowlurereport()
    @commands.has_permissions(manage_channels=True)
    async def reset(self, ctx, *, report_message=None):
        """Resets all lure reports.

        Usage: !lure reset"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel

        # get settings
        lure_dict = copy.deepcopy(self.bot.guild_dict[guild.id].setdefault('lure_dict', {}))
        await utils.safe_delete(message)

        if not lure_dict:
            return
        if report_message and int(report_message) in lure_dict.keys():
            report_message = await channel.fetch_message(report_message)
            await self.expire_lure(report_message)
            return
        rusure = await channel.send(_('**Meowth!** Are you sure you\'d like to remove all lures?'))
        try:
            timeout = False
            res, reactuser = await utils.ask(self.bot, rusure, author.id)
        except TypeError:
            timeout = True
        if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', '\u274e'):
            await utils.safe_delete(rusure)
            confirmation = await channel.send(_('Manual reset cancelled.'), delete_after=10)
            return
        elif res.emoji == self.bot.custom_emoji.get('answer_yes', '\u2705'):
            await utils.safe_delete(rusure)
            async with ctx.typing():
                for report in lure_dict:
                    report_message = await channel.fetch_message(report)
                    self.bot.loop.create_task(self.expire_lure(report_message))
                confirmation = await channel.send(_('Lures reset.'), delete_after=10)
                return
        else:
            return

def setup(bot):
    bot.add_cog(Lure(bot))

def teardown(bot):
    bot.remove_cog(Lure)
