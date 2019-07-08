import asyncio
import copy
import re
import time
import datetime
import dateparser
import textwrap
import logging
import string
import random

import discord
from discord.ext import commands, tasks

from meowth import checks
from meowth.exts import pokemon as pkmn_class
from meowth.exts import utilities as utils

logger = logging.getLogger("meowth")

class Pvp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pvp_cleanup.start()

    def cog_unload(self):
        self.pvp_cleanup.cancel()

    @tasks.loop(seconds=0)
    async def pvp_cleanup(self, loop=True):
        logger.info('------ BEGIN ------')
        guilddict_temp = copy.deepcopy(self.bot.guild_dict)
        expire_list = []
        count = 0
        for guildid in guilddict_temp.keys():
            pvp_dict = guilddict_temp[guildid].setdefault('pvp_dict', {})
            for reportid in pvp_dict.keys():
                if pvp_dict[reportid].get('exp', 0) <= time.time():
                    report_channel = self.bot.get_channel(pvp_dict[reportid].get('report_channel'))
                    if report_channel:
                        try:
                            report_message = await report_channel.fetch_message(reportid)
                            self.bot.loop.create_task(self.expire_pvp(report_message))
                            count += 1
                            continue
                        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                            pass
                    try:
                        self.bot.loop.create_task(utils.expire_dm_reports(self.bot, pvp_dict.get(reportid, {}).get('dm_dict', {})))
                        del self.bot.guild_dict[guildid]['pvp_dict'][reportid]
                        count += 1
                        continue
                    except KeyError:
                        continue
                to_expire = pvp_dict[reportid].get('exp', 0) - time.time()
                if to_expire > 0:
                    expire_list.append(to_expire)
        # save server_dict changes after cleanup
        logger.info('SAVING CHANGES')
        try:
            await self.bot.save
        except Exception as err:
            logger.info('SAVING FAILED' + err)
            pass
        if not expire_list:
            expire_list = [600]
        logger.info(f"------ END - {count} PVPs Cleaned - Waiting {min(expire_list)} seconds. ------")
        if not loop:
            return
        self.pvp_cleanup.change_interval(seconds=min(expire_list))

    @pvp_cleanup.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    async def expire_pvp(self, message):
        guild = message.channel.guild
        channel = message.channel
        pvp_dict = copy.deepcopy(self.bot.guild_dict[guild.id]['pvp_dict'])
        if not pvp_dict[message.id].get('tournament', {}).get('status', None) == "complete":
            await utils.safe_delete(message)
        try:
            user_message = await channel.fetch_message(pvp_dict[message.id]['report_message'])
            await utils.safe_delete(user_message)
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, KeyError):
            pass
        await utils.expire_dm_reports(self.bot, pvp_dict.get(message.id, {}).get('dm_dict', {}))
        try:
            del self.bot.guild_dict[guild.id]['pvp_dict'][message.id]
        except KeyError:
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        channel = self.bot.get_channel(payload.channel_id)
        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.errors.NotFound, AttributeError, discord.Forbidden):
            return
        guild = message.guild
        try:
            user = guild.get_member(payload.user_id)
        except AttributeError:
            return
        guild = message.guild
        emoji = payload.emoji.name
        try:
            pvp_dict = self.bot.guild_dict[guild.id]['pvp_dict']
        except KeyError:
            pvp_dict = {}
        if message.id in pvp_dict and pvp_dict.get(message.id, {}).get('tournament') and user.id != self.bot.user.id:
            embed = message.embeds[0]
            pvp_dict = self.bot.guild_dict[guild.id]['pvp_dict'][message.id]
            round = pvp_dict['tournament']['round']
            if pvp_dict['tournament']['round'] == 0:
                if "\u20e3" in emoji and user.id not in pvp_dict['tournament']['trainers']:
                    i = int(emoji[0])
                    pvp_dict['tournament']['trainers'].append(user.id)
                    user_list = [self.bot.get_user(x) for x in pvp_dict['tournament']['trainers']]
                    user_list = [x.mention for x in user_list]
                    await message.remove_reaction(emoji, self.bot.user)
                    new_embed = discord.Embed(colour=guild.me.colour).set_thumbnail(url=embed.thumbnail.url).set_author(name=embed.author.name, icon_url=embed.author.icon_url).set_footer(text=embed.footer.text, icon_url=embed.footer.icon_url)
                    new_embed.add_field(name=embed.fields[0].name, value=embed.fields[0].value, inline=embed.fields[0].inline)
                    new_embed.add_field(name=embed.fields[1].name, value=embed.fields[1].value, inline=embed.fields[1].inline)
                    new_embed.add_field(name="Trainers Joined", value=(', ').join(user_list), inline=False)
                    await message.edit(embed=new_embed)
                elif emoji == self.bot.custom_emoji.get('pvp_start', '\u25B6') and user.id == pvp_dict['tournament']['creator'] and len(pvp_dict['tournament']['trainers']) == pvp_dict['tournament']['size']:
                    ctx = await self.bot.get_context(message)
                    if len(pvp_dict['tournament']['trainers']) == 8:
                        await self.bracket_8(ctx)
                    elif len(pvp_dict['tournament']['trainers']) == 4:
                        await self.bracket_4(ctx)
                    elif len(pvp_dict['tournament']['trainers']) == 2:
                        await self.bracket_2(ctx)
                    return
            else:
                if "\u20e3" in emoji and user.id == pvp_dict['tournament']['creator']:
                    trainer_list = copy.deepcopy(pvp_dict['tournament']['bracket'][0])
                    i = int(emoji[0])
                    winner_list = pvp_dict['tournament']['winners'].get(round, [])
                    winner_list.append(trainer_list[i-1])
                    pvp_dict['tournament']['winners'][round] = winner_list
                    if i%2 == 0:
                        try:
                            await message.remove_reaction(f"{i-1}\u20e3", self.bot.user)
                        except:
                            pass
                    else:
                        try:
                            await message.remove_reaction(f"{i+1}\u20e3", self.bot.user)
                        except:
                            pass
                    await message.remove_reaction(emoji, self.bot.user)
                    await message.remove_reaction(emoji, user)
                    user_list = [self.bot.get_user(x) for x in winner_list]
                    user_list = [x.mention for x in user_list]
                    new_embed = discord.Embed(colour=guild.me.colour).set_thumbnail(url=embed.thumbnail.url).set_author(name=embed.author.name, icon_url=embed.author.icon_url).set_footer(text=embed.footer.text, icon_url=embed.footer.icon_url)
                    if pvp_dict['tournament']['next_size'] == 1:
                        first_place = self.bot.get_user(pvp_dict['tournament']['trainers'][i-1])
                        second_place = copy.deepcopy(pvp_dict['tournament']['bracket'][round-1])
                        second_place.remove(first_place.id)
                        second_place = self.bot.get_user(second_place[0])
                        new_embed.clear_fields()
                        new_embed.add_field(name=embed.fields[0].name, value=embed.fields[0].value, inline=embed.fields[0].inline)
                        new_embed.add_field(name=embed.fields[1].name, value=embed.fields[1].value, inline=embed.fields[1].inline)
                        new_embed.add_field(name="\U0001F947 First Place \U0001F947", value=first_place.mention, inline=True)
                        new_embed.add_field(name="\U0001F948 Second Place \U0001F948", value=second_place.mention, inline=True)
                        pvp_dict['tournament']['status'] = "complete"
                        await message.clear_reactions()
                        edit_content = message.content.split("\n")[0] + " has ended! congratulations to the winner!"
                    else:
                        new_embed.clear_fields()
                        for field in embed.fields:
                            if "winners" not in field.name.lower():
                                new_embed.add_field(name=field.name, value=field.value, inline=field.inline)
                        new_embed.add_field(name="Round Winners", value=(', ').join(user_list), inline=False)
                        edit_content = message.content
                    await message.edit(content=edit_content, embed=new_embed)
                    pvp_dict['tournament']['trainers'] = winner_list
                elif emoji == self.bot.custom_emoji.get('pvp_start', '\u25B6') and user.id == pvp_dict['tournament']['creator'] and  len(pvp_dict['tournament']['trainers']) == pvp_dict['tournament']['next_size']:
                    ctx = await self.bot.get_context(message)
                    if len(pvp_dict['tournament']['trainers']) == 8:
                        await self.bracket_8(ctx)
                    elif len(pvp_dict['tournament']['trainers']) == 4:
                        await self.bracket_4(ctx)
                    elif len(pvp_dict['tournament']['trainers']) == 2:
                        await self.bracket_2(ctx)
                    return
            if emoji == self.bot.custom_emoji.get('pvp_stop', '\u23f9') and user.id == pvp_dict['tournament']['creator']:
                await self.expire_pvp(message)
                return
            await message.remove_reaction(emoji, user)
            return

    async def bracket_8(self, ctx):
        message = ctx.message
        guild = ctx.guild
        pvp_dict = self.bot.guild_dict[guild.id]['pvp_dict'][message.id]
        embed = message.embeds[0]
        start_emoji = self.bot.custom_emoji.get('pvp_start', '\u25B6')
        stop_emoji = self.bot.custom_emoji.get('pvp_stop', '\u23f9')
        new_embed = discord.Embed(colour=guild.me.colour).set_thumbnail(url=embed.thumbnail.url).set_author(name=embed.author.name, icon_url=embed.author.icon_url).set_footer(text=embed.footer.text, icon_url=embed.footer.icon_url)
        new_embed.add_field(name=embed.fields[0].name, value=embed.fields[0].value, inline=embed.fields[0].inline)
        new_embed.add_field(name=embed.fields[1].name, value=embed.fields[1].value, inline=embed.fields[1].inline)
        trainer_list = pvp_dict['tournament']['trainers']
        round = pvp_dict['tournament']['round']
        creator = self.bot.get_user(pvp_dict['tournament']['creator'])
        random.shuffle(trainer_list)
        random.shuffle(trainer_list)
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][message.id]['tournament']['bracket'][round] = copy.copy(trainer_list)
        round = round + 1
        trainer_mentions = [self.bot.get_user(x) for x in trainer_list]
        trainer_mentions = [x.mention for x in trainer_mentions]
        trainer_mentions.insert(0, None)
        new_embed.add_field(name=f"**Round {round} Match 1:**", value=f"1\u20e3 {trainer_mentions[1]} **VS** {trainer_mentions[2]} 2\u20e3")
        new_embed.add_field(name=f"**Round {round} Match 2:**", value=f"3\u20e3 {trainer_mentions[3]} **VS** {trainer_mentions[4]} 4\u20e3")
        new_embed.add_field(name=f"**Round {round} Match 3:**", value=f"5\u20e3 {trainer_mentions[5]} **VS** {trainer_mentions[6]} 6\u20e3")
        new_embed.add_field(name=f"**Round {round} Match 4:**", value=f"7\u20e3 {trainer_mentions[7]} **VS** {trainer_mentions[8]} 8\u20e3")
        trainer_mentions.remove(None)
        await ctx.message.edit(content=f"PVP Tournament started by {creator.mention}\n\n{creator.mention}, react with the emoji 1\u20e3 through {len(trainer_list)}\u20e3 that matches the **winner** of each match!\n\n{creator.mention} can react with {start_emoji} to go to next round once all matches are decided, or react with {stop_emoji} to cancel the tournament.", embed=new_embed)
        await ctx.message.clear_reactions()
        for i in range(8):
            await utils.safe_reaction(ctx.message, f'{i+1}\u20e3')
        await utils.safe_reaction(ctx.message, start_emoji)
        await utils.safe_reaction(ctx.message, stop_emoji)
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][message.id]['tournament']['round'] = round
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][message.id]['tournament']['trainers'] = trainer_list
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][message.id]['tournament']['next_size'] = 4
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][message.id]['tournament']['status'] = "active"

    async def bracket_4(self, ctx):
        message = ctx.message
        guild = ctx.guild
        pvp_dict = self.bot.guild_dict[guild.id]['pvp_dict'][message.id]
        embed = message.embeds[0]
        start_emoji = self.bot.custom_emoji.get('pvp_start', '\u25B6')
        stop_emoji = self.bot.custom_emoji.get('pvp_stop', '\u23f9')
        new_embed = discord.Embed(colour=guild.me.colour).set_thumbnail(url=embed.thumbnail.url).set_author(name=embed.author.name, icon_url=embed.author.icon_url).set_footer(text=embed.footer.text, icon_url=embed.footer.icon_url)
        new_embed.add_field(name=embed.fields[0].name, value=embed.fields[0].value, inline=embed.fields[0].inline)
        new_embed.add_field(name=embed.fields[1].name, value=embed.fields[1].value, inline=embed.fields[1].inline)
        trainer_list = pvp_dict['tournament']['trainers']
        round = pvp_dict['tournament']['round']
        creator = self.bot.get_user(pvp_dict['tournament']['creator'])
        random.shuffle(trainer_list)
        random.shuffle(trainer_list)
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][message.id]['tournament']['bracket'][round] = copy.copy(trainer_list)
        round = round + 1
        trainer_mentions = [self.bot.get_user(x) for x in trainer_list]
        trainer_mentions = [x.mention for x in trainer_mentions]
        trainer_mentions.insert(0, None)
        new_embed.add_field(name=f"**Round {round} Match 1:**", value=f"1\u20e3 {trainer_mentions[1]} **VS** {trainer_mentions[2]} 2\u20e3")
        new_embed.add_field(name=f"**Round {round} Match 2:**", value=f"3\u20e3 {trainer_mentions[3]} **VS** {trainer_mentions[4]} 4\u20e3")
        trainer_mentions.remove(None)
        await ctx.message.edit(content=f"PVP Tournament started by {creator.mention}\n\n{creator.mention}, react with the emoji 1\u20e3 through {len(trainer_list)}\u20e3 for each winner of each match!\n\n{creator.mention} can react with {start_emoji} to go to next round once all matches are decided, or react with {stop_emoji} to cancel the tournament.", embed=new_embed)
        await ctx.message.clear_reactions()
        for i in range(4):
            await utils.safe_reaction(ctx.message, f'{i+1}\u20e3')
        await utils.safe_reaction(ctx.message, start_emoji)
        await utils.safe_reaction(ctx.message, stop_emoji)
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][message.id]['tournament']['round'] = round
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][message.id]['tournament']['trainers'] = trainer_list
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][message.id]['tournament']['next_size'] = 2
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][message.id]['tournament']['status'] = "active"

    async def bracket_2(self, ctx):
        message = ctx.message
        guild = ctx.guild
        pvp_dict = self.bot.guild_dict[guild.id]['pvp_dict'][message.id]
        embed = message.embeds[0]
        start_emoji = self.bot.custom_emoji.get('pvp_start', '\u25B6')
        stop_emoji = self.bot.custom_emoji.get('pvp_stop', '\u23f9')
        new_embed = discord.Embed(colour=guild.me.colour).set_thumbnail(url=embed.thumbnail.url).set_author(name=embed.author.name, icon_url=embed.author.icon_url).set_footer(text=embed.footer.text, icon_url=embed.footer.icon_url)
        new_embed.add_field(name=embed.fields[0].name, value=embed.fields[0].value, inline=embed.fields[0].inline)
        new_embed.add_field(name=embed.fields[1].name, value=embed.fields[1].value, inline=embed.fields[1].inline)
        trainer_list = pvp_dict['tournament']['trainers']
        round = pvp_dict['tournament']['round']
        creator = self.bot.get_user(pvp_dict['tournament']['creator'])
        random.shuffle(trainer_list)
        random.shuffle(trainer_list)
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][message.id]['tournament']['bracket'][round] = copy.copy(trainer_list)
        round = round + 1
        trainer_mentions = [self.bot.get_user(x) for x in trainer_list]
        trainer_mentions = [x.mention for x in trainer_mentions]
        trainer_mentions.insert(0, None)
        new_embed.add_field(name=f"**Round {round} Match 1:**", value=f"1\u20e3 {trainer_mentions[1]} **VS** {trainer_mentions[2]} 2\u20e3")
        trainer_mentions.remove(None)
        await ctx.message.edit(content=f"PVP Tournament started by {creator.mention}\n\n{creator.mention}, react with the emoji 1\u20e3 through {len(trainer_list)}\u20e3 for each winner of each match!\n\n{creator.mention} can react with {start_emoji} to go to next round once all matches are decided, or react with {stop_emoji} to cancel the tournament.", embed=new_embed)
        await ctx.message.clear_reactions()
        for i in range(2):
            await utils.safe_reaction(ctx.message, f'{i+1}\u20e3')
        await utils.safe_reaction(ctx.message, start_emoji)
        await utils.safe_reaction(ctx.message, stop_emoji)
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][message.id]['tournament']['round'] = round
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][message.id]['tournament']['trainers'] = trainer_list
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][message.id]['tournament']['next_size'] = 1
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][message.id]['tournament']['status'] = "active"

    @commands.group(invoke_without_command=True, case_insensitive=True)
    @checks.allowpvpreport()
    async def pvp(self, ctx, pvp_type=None, *, location:commands.clean_content(fix_channel_mentions=True)="", timer="30"):
        """Report a PVP battle request.

        Usage: !pvp [type] [location] [minutes]
        Guided report available with just !pvp"""
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset']))
        error = False
        pvp_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/CombatButton.png?cache=1')
        pvp_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        while True:
            async with ctx.typing():
                if pvp_type and any([pvp_type.lower() == "any", pvp_type.lower() == "great", pvp_type.lower() == "ultra", pvp_type.lower() == "master"]) and location:
                    if location.split()[-1].isdigit():
                        timer = location.split()[-1]
                        location = location.replace(timer, '').strip()
                    if int(timer) > 720:
                        timer = "720"
                    await self._pvp(ctx, pvp_type, location, timer)
                    return
                else:
                    pvp_embed.add_field(name=_('**New PVP Request**'), value=_("Meowth! I'll help you report a PVP battle!\n\nFirst, I'll need to know what **type** of PVP battle you'd like to start. Reply with the **any, great, ultra, or master**. You can reply with **cancel** to stop anytime."), inline=False)
                    pvp_type_wait = await channel.send(embed=pvp_embed)
                    def check(reply):
                        if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                            return True
                        else:
                            return False
                    try:
                        pvp_type_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        pvp_type_msg = None
                    await utils.safe_delete(pvp_type_wait)
                    if not pvp_type_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(pvp_type_msg)
                    if pvp_type_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif not any([pvp_type_msg.clean_content.lower() == "any", pvp_type_msg.clean_content.lower() == "great", pvp_type_msg.clean_content.lower() == "ultra", pvp_type_msg.clean_content.lower() == "master"]):
                        error = _("entered an invalid type")
                        break
                    else:
                        pvp_type = pvp_type_msg.clean_content.lower()
                        if pvp_type != "any":
                            pvp_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/pogo_{pvp_type}_league.png?cache=1")
                    pvp_embed.clear_fields()
                    pvp_embed.add_field(name="**New PVP Request**", value=f"Great! Now, reply with the **location** that you will be at for **{pvp_type} PVP** battles. You can reply with **cancel** to stop anytime.", inline=False)
                    location_wait = await channel.send(embed=pvp_embed)
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
                    pvp_embed.clear_fields()
                    pvp_embed.add_field(name="**New PVP Request**", value=f"Fantastic! Now, reply with the **minutes remaining** that you'll be available for **{pvp_type} PVP** battles. You can reply with **cancel** to stop anytime.", inline=False)
                    expire_wait = await channel.send(embed=pvp_embed)
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
                    elif not expire_msg.clean_content.isdigit():
                        error = _("didn't enter a number")
                        break
                    elif int(expire_msg.clean_content) > 720:
                        timer = "720"
                    elif expire_msg:
                        timer = expire_msg.clean_content
                    pvp_embed.remove_field(0)
                    break
        if not error:
            await self._pvp(ctx, pvp_type, location, timer)
        else:
            pvp_embed.clear_fields()
            pvp_embed.add_field(name=_('**PVP Request Cancelled**'), value=_("Meowth! Your report has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=pvp_embed, delete_after=10)
            await utils.safe_delete(message)

    async def _pvp(self, ctx, pvp_type, location, timer):
        dm_dict = {}
        pvp_dict = self.bot.guild_dict[ctx.guild.id].setdefault('pvp_dict', {})
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.message.channel.guild.id]['configure_dict']['settings']['offset']))
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['offset'])
        end = now + datetime.timedelta(minutes=int(timer))
        pvp_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey.png?cache=1')
        pvp_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=ctx.author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=ctx.author.avatar_url_as(format=None, static_format='jpg', size=32))
        pvp_msg = _("PVP Requested by {author}").format(author=ctx.author.mention)
        pvp_embed.title = _('Meowth! Click here for my directions to the PVP!')
        pvp_embed.description = f"Ask {ctx.author.name} if my directions aren't perfect!\n**Location:** {location}"
        loc_url = utils.create_gmaps_query(self.bot, location, ctx.channel, type="pvp")
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        stop_info = ""
        if gym_matching_cog:
            stop_info, location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "pvp", dupe_check=False)
            if stop_url:
                loc_url = stop_url
                pvp_embed.description = stop_info
        if not location:
            return
        pvp_embed.url = loc_url
        item = None
        pvp_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/CombatButton.png")
        pvp_embed.set_author(name=f"PVP Request", icon_url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/CombatButton.png?cache=1")
        if pvp_type != "any":
            pvp_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/pogo_{pvp_type}_league.png")
            pvp_embed.set_author(name=f"{pvp_type.title()} League PVP Request", icon_url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/pogo_{pvp_type}_league.png?cache=1")
        pvp_embed.add_field(name=f"**PVP Type:**", value=pvp_type.title())
        pvp_embed.add_field(name=f"**Available Until:**", value=end.strftime(_('%I:%M %p (%H:%M)')))
        confirmation = await ctx.channel.send(pvp_msg, embed=pvp_embed)
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][confirmation.id] = {
            'exp':time.time() + int(timer)*60,
            'expedit':"delete",
            'report_message':ctx.message.id,
            'report_channel':ctx.channel.id,
            'report_author':ctx.author.id,
            'report_guild':ctx.guild.id,
            'dm_dict':dm_dict,
            'location':location,
            'url':loc_url,
            'type':pvp_type
        }

    @pvp.command()
    @checks.allowpvpreport()
    async def tournament(self, ctx, size="8", pvp_type=None, *, location:commands.clean_content(fix_channel_mentions=True)=""):
        """Report a PVP battle request.

        Usage: !pvp tournament [size] [type] [location]
        Guided report available with just !pvp"""
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset']))
        error = False
        pvp_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/CombatButton.png?cache=1')
        pvp_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        while True:
            async with ctx.typing():
                if pvp_type and any([pvp_type.lower() == "any", pvp_type.lower() == "great", pvp_type.lower() == "ultra", pvp_type.lower() == "master"]) and location:
                    await self._pvp_tournament(ctx, size, pvp_type, location)
                    return
                else:
                    pvp_embed.add_field(name=_('**New PVP Tournament**'), value=_("Meowth! I'll help you report a PVP Tournament!\n\nFirst, I'll need to know what **size** of PVP tournament you'd like to start. Reply with a currently supported size: **2, 4, 8**. You can reply with **cancel** to stop anytime."), inline=False)
                    pvp_size_wait = await channel.send(embed=pvp_embed)
                    def check(reply):
                        if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                            return True
                        else:
                            return False
                    try:
                        pvp_size_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        pvp_size_msg = None
                    await utils.safe_delete(pvp_size_wait)
                    if not pvp_size_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(pvp_size_msg)
                    if pvp_size_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif not any([pvp_size_msg.clean_content.lower() == "2", pvp_size_msg.clean_content.lower() == "4", pvp_size_msg.clean_content.lower() == "8"]):
                        error = _("entered an invalid size")
                        break
                    else:
                        size = pvp_size_msg.clean_content.lower()
                    pvp_embed.clear_fields()
                    pvp_embed.add_field(name=_('**New PVP Tournament**'), value=_("Next, I'll need to know what **type** of PVP tournament you'd like to start. Reply with **great, ultra, or master**. You can reply with **cancel** to stop anytime."), inline=False)
                    pvp_type_wait = await channel.send(embed=pvp_embed)
                    def check(reply):
                        if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                            return True
                        else:
                            return False
                    try:
                        pvp_type_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        pvp_type_msg = None
                    await utils.safe_delete(pvp_type_wait)
                    if not pvp_type_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(pvp_type_msg)
                    if pvp_type_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif not any([pvp_type_msg.clean_content.lower() == "great", pvp_type_msg.clean_content.lower() == "ultra", pvp_type_msg.clean_content.lower() == "master"]):
                        error = _("entered an invalid type")
                        break
                    else:
                        pvp_type = pvp_type_msg.clean_content.lower()
                        pvp_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/pogo_{pvp_type}_league.png?cache=1")
                    pvp_embed.clear_fields()
                    pvp_embed.add_field(name="**New PVP Tournament**", value=f"Great! Now, reply with the **location** that you will be at for **{pvp_type} PVP** battles. You can reply with **cancel** to stop anytime.", inline=False)
                    location_wait = await channel.send(embed=pvp_embed)
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
                        poi_info = ""
                        if gym_matching_cog:
                            poi_info, location, poi_url = await gym_matching_cog.get_poi_info(ctx, location, "pvp")
                            if poi_url:
                                loc_url = poi_url
                        if not location:
                            return
        if not error:
            await self._pvp_tournament(ctx,size,  pvp_type, location)
        else:
            pvp_embed.clear_fields()
            pvp_embed.add_field(name=_('**PVP Tournament Cancelled**'), value=_("Meowth! Your report has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=pvp_embed, delete_after=10)
            await utils.safe_delete(message)

    async def _pvp_tournament(self, ctx, size, pvp_type, location):
        dm_dict = {}
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.message.channel.guild.id]['configure_dict']['settings']['offset']))
        start_emoji = self.bot.custom_emoji.get('pvp_start', '\u25B6')
        stop_emoji = self.bot.custom_emoji.get('pvp_stop', '\u23f9')
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['offset'])
        pvp_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey.png?cache=1')
        pvp_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=ctx.author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=ctx.author.avatar_url_as(format=None, static_format='jpg', size=32))
        pvp_msg = f"PVP Tournament started by {ctx.author.mention} - React with 1\u20e3 through {size}\u20e3 to join!\n\n{ctx.author.mention} can react with {start_emoji} to start the tournament once {size} trainers have joined, or react with {stop_emoji} to cancel the tournament."
        pvp_embed.title = _('Meowth! Click here for my directions to the PVP!')
        pvp_embed.description = f"Ask {ctx.author.name} if my directions aren't perfect!\n**Location:** {location}"
        loc_url = utils.create_gmaps_query(self.bot, location, ctx.channel, type="pvp")
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        stop_info = ""
        if gym_matching_cog:
            stop_info, location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "pvp", dupe_check=False)
            if stop_url:
                loc_url = stop_url
                pvp_embed.description = stop_info
        if not location:
            return
        pvp_embed.url = loc_url
        item = None
        pvp_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/pogo_{pvp_type}_league.png")
        pvp_embed.set_author(name=f"{pvp_type.title()} League PVP Tournament", icon_url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/pogo_{pvp_type}_league.png?cache=1")
        pvp_embed.add_field(name=f"**PVP Type:**", value=pvp_type.title())
        pvp_embed.add_field(name=f"**Tournament Size:**", value=str(size))
        confirmation = await ctx.channel.send(pvp_msg, embed=pvp_embed)
        for i in range(int(size)):
            await utils.safe_reaction(confirmation, f'{i+1}\u20e3')
        await utils.safe_reaction(confirmation, start_emoji)
        await utils.safe_reaction(confirmation, stop_emoji)
        test_var = self.bot.guild_dict[ctx.guild.id].setdefault('pvp_dict', {}).setdefault(confirmation.id, {})
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][confirmation.id] = {
            'exp':time.time() + 4*60*60,
            'expedit':"delete",
            'report_message':ctx.message.id,
            'report_channel':ctx.channel.id,
            'report_author':ctx.author.id,
            'report_guild':ctx.guild.id,
            'dm_dict':dm_dict,
            'location':location,
            'url':loc_url,
            'type':pvp_type,
            'tournament':{
                'creator':ctx.author.id,
                'size':int(size),
                'trainers':[],
                'round':0,
                'bracket':{},
                'winners':{},
                'status':"starting"
            }
        }

    @pvp.command(aliases=['expire'])
    @checks.allowpvpreport()
    @commands.has_permissions(manage_channels=True)
    async def reset(self, ctx, *, report_message=None):
        """Resets all PVP requests."""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel

        # get settings
        pvp_dict = copy.deepcopy(self.bot.guild_dict[guild.id].setdefault('pvp_dict', {}))
        await utils.safe_delete(message)

        if not pvp_dict:
            return
        if report_message and int(report_message) in pvp_dict.keys():
            report_message = await channel.fetch_message(report_message)
            await self.expire_pvp(report_message)
            return
        rusure = await channel.send(_('**Meowth!** Are you sure you\'d like to remove all PVP requests?'))
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
            for report in pvp_dict:
                report_message = await channel.fetch_message(report)
                self.bot.loop.create_task(self.expire_pvp(report_message))
            confirmation = await channel.send(_('PVPs reset.'), delete_after=10)
            return
        else:
            return

def setup(bot):
    bot.add_cog(Pvp(bot))

def teardown(bot):
    bot.remove_cog(Pvp)
