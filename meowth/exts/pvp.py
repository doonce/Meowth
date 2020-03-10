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
import traceback

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
        expire_list = []
        count = 0
        for guild in list(self.bot.guilds):
            if guild.id not in list(self.bot.guild_dict.keys()):
                continue
            try:
                pvp_dict = self.bot.guild_dict[guild.id].setdefault('pvp_dict', {})
                for reportid in list(pvp_dict.keys()):
                    if pvp_dict.get(reportid, {}).get('exp', 0) <= time.time():
                        report_channel = self.bot.get_channel(pvp_dict.get(reportid, {}).get('report_channel'))
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
                            del self.bot.guild_dict[guild.id]['pvp_dict'][reportid]
                            count += 1
                            continue
                        except KeyError:
                            continue
                    to_expire = pvp_dict.get(reportid, {}).get('exp', 0) - time.time()
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
        last_report = True if len (self.bot.guild_dict[guild.id]['pvp_dict'].keys()) == 1 else False
        if not pvp_dict[message.id].get('tournament', {}).get('status', None) == "complete":
            cleanup_setting = self.bot.guild_dict[guild.id].get('configure_dict', {}).get('pvp', {}).setdefault('cleanup_setting', "delete")
            if cleanup_setting == "delete":
                await utils.safe_delete(message)
            else:
                try:
                    await message.edit(content=message.content.splitlines()[0], embed=discord.Embed(colour=message.guild.me.colour, description=f"**This PVP has expired!**"))
                    await message.clear_reactions()
                except:
                    pass
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
        try:
            ctx = await self.bot.get_context(message)
            if last_report and len (self.bot.guild_dict[guild.id]['pvp_dict'].keys()) == 0:
                await ctx.invoke(self.bot.get_command('list pvp'))
        except:
            pass

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
        can_manage = channel.permissions_for(user).manage_messages
        emoji = payload.emoji.name
        try:
            pvp_dict = self.bot.guild_dict[guild.id]['pvp_dict']
        except KeyError:
            pvp_dict = {}
        if message.id in pvp_dict:
            pvp_dict = self.bot.guild_dict[guild.id]['pvp_dict'][message.id]
            if str(payload.emoji) == self.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f'):
                ctx = await self.bot.get_context(message)
                await asyncio.sleep(0.25)
                await utils.remove_reaction(message, payload.emoji, self.bot.user)
                await asyncio.sleep(0.25)
                await utils.remove_reaction(message, payload.emoji, user)
                await ctx.invoke(self.bot.get_command("list pvp"))
                await asyncio.sleep(5)
                return await utils.add_reaction(message, payload.emoji)
            elif str(payload.emoji) == self.bot.custom_emoji.get('pvp_report', u'\U0001F4E2'):
                ctx = await self.bot.get_context(message)
                ctx.author, ctx.message.author = user, user
                await utils.remove_reaction(message, payload.emoji, user)
                return await ctx.invoke(self.bot.get_command('pvp'))
            elif str(payload.emoji) == self.bot.custom_emoji.get('pvp_stop', u'\U000023f9\U0000fe0f'):
                for reaction in message.reactions:
                    if reaction.emoji == self.bot.custom_emoji.get('pvp_stop', u'\U000023f9\U0000fe0f') and (reaction.count >= 3 or can_manage or user.id == pvp_dict['report_author']):
                        await self.expire_pvp(message)
            if pvp_dict.get('tournament'):
                embed = message.embeds[0]
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
                    elif emoji == self.bot.custom_emoji.get('pvp_start', u'\U000025b6\U0000fe0f') and user.id == pvp_dict['tournament']['creator'] and len(pvp_dict['tournament']['trainers']) == pvp_dict['tournament']['size']:
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
                            edit_content = message.content.split("\n")[0] + " has ended! Congratulations to the winner!"
                            if pvp_dict['tournament']['official']:
                                for trainer in pvp_dict['tournament']['trainers']:
                                    if trainer != first_place.id:
                                        pvp_record = self.bot.guild_dict[message.guild.id].setdefault('trainers', {}).setdefault(trainer, {}).setdefault('pvp', {}).setdefault('record', {}).setdefault('loss', 0) + 1
                                        self.bot.guild_dict[message.guild.id]['trainers'][trainer]['pvp']['record']['loss'] = pvp_record
                                    elif trainer == first_place.id:
                                        pvp_record = self.bot.guild_dict[message.guild.id].setdefault('trainers', {}).setdefault(trainer, {}).setdefault('pvp', {}).setdefault('record', {}).setdefault('win', 0) + 1
                                        self.bot.guild_dict[message.guild.id]['trainers'][trainer]['pvp']['record']['win'] = pvp_record
                        else:
                            new_embed.clear_fields()
                            for field in embed.fields:
                                if "winners" not in field.name.lower():
                                    new_embed.add_field(name=field.name, value=field.value, inline=field.inline)
                            new_embed.add_field(name="Round Winners", value=(', ').join(user_list), inline=False)
                            edit_content = message.content
                        await message.edit(content=edit_content, embed=new_embed)
                        pvp_dict['tournament']['trainers'] = winner_list
                    elif emoji == self.bot.custom_emoji.get('pvp_start', u'\U000025b6\U0000fe0f') and user.id == pvp_dict['tournament']['creator'] and  len(pvp_dict['tournament']['trainers']) == pvp_dict['tournament']['next_size']:
                        ctx = await self.bot.get_context(message)
                        if len(pvp_dict['tournament']['trainers']) == 8:
                            await self.bracket_8(ctx)
                        elif len(pvp_dict['tournament']['trainers']) == 4:
                            await self.bracket_4(ctx)
                        elif len(pvp_dict['tournament']['trainers']) == 2:
                            await self.bracket_2(ctx)
                        return
                if emoji == self.bot.custom_emoji.get('pvp_stop', u'\U000023f9\U0000fe0f') and user.id == pvp_dict['tournament']['creator']:
                    await self.expire_pvp(message)
                    return
                await message.remove_reaction(emoji, user)
                return

    async def bracket_8(self, ctx):
        message = ctx.message
        guild = ctx.guild
        pvp_dict = self.bot.guild_dict[guild.id]['pvp_dict'][message.id]
        embed = message.embeds[0]
        start_emoji = self.bot.custom_emoji.get('pvp_start', u'\U000025b6\U0000fe0f')
        stop_emoji = self.bot.custom_emoji.get('pvp_stop', u'\U000023f9\U0000fe0f')
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
        new_embed.add_field(name=f"**Round {round} Match 1:**", value=f"1\u20e3 {trainer_mentions[1]} **VS** {trainer_mentions[2]} 2\u20e3", inline=False)
        new_embed.add_field(name=f"**Round {round} Match 2:**", value=f"3\u20e3 {trainer_mentions[3]} **VS** {trainer_mentions[4]} 4\u20e3", inline=False)
        new_embed.add_field(name=f"**Round {round} Match 3:**", value=f"5\u20e3 {trainer_mentions[5]} **VS** {trainer_mentions[6]} 6\u20e3", inline=False)
        new_embed.add_field(name=f"**Round {round} Match 4:**", value=f"7\u20e3 {trainer_mentions[7]} **VS** {trainer_mentions[8]} 8\u20e3", inline=False)
        trainer_mentions.remove(None)
        await ctx.message.edit(content=f"PVP Tournament started by {creator.mention}\n\n{creator.mention}, react with the emoji 1\u20e3 through {len(trainer_list)}\u20e3 that matches the **winner** of each match!\n\n{creator.mention} can react with {start_emoji} to go to next round once all matches are decided, or react with {stop_emoji} to cancel the tournament.", embed=new_embed)
        await ctx.message.clear_reactions()
        for i in range(8):
            await utils.add_reaction(ctx.message, f'{i+1}\u20e3')
        await utils.add_reaction(ctx.message, start_emoji)
        await utils.add_reaction(ctx.message, stop_emoji)
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][message.id]['tournament']['round'] = round
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][message.id]['tournament']['trainers'] = trainer_list
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][message.id]['tournament']['next_size'] = 4
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][message.id]['tournament']['status'] = "active"

    async def bracket_4(self, ctx):
        message = ctx.message
        guild = ctx.guild
        pvp_dict = self.bot.guild_dict[guild.id]['pvp_dict'][message.id]
        embed = message.embeds[0]
        start_emoji = self.bot.custom_emoji.get('pvp_start', u'\U000025b6\U0000fe0f')
        stop_emoji = self.bot.custom_emoji.get('pvp_stop', u'\U000023f9\U0000fe0f')
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
        new_embed.add_field(name=f"**Round {round} Match 1:**", value=f"1\u20e3 {trainer_mentions[1]} **VS** {trainer_mentions[2]} 2\u20e3", inline=False)
        new_embed.add_field(name=f"**Round {round} Match 2:**", value=f"3\u20e3 {trainer_mentions[3]} **VS** {trainer_mentions[4]} 4\u20e3", inline=False)
        trainer_mentions.remove(None)
        await ctx.message.edit(content=f"PVP Tournament started by {creator.mention}\n\n{creator.mention}, react with the emoji 1\u20e3 through {len(trainer_list)}\u20e3 for each winner of each match!\n\n{creator.mention} can react with {start_emoji} to go to next round once all matches are decided, or react with {stop_emoji} to cancel the tournament.", embed=new_embed)
        await ctx.message.clear_reactions()
        for i in range(4):
            await utils.add_reaction(ctx.message, f'{i+1}\u20e3')
        await utils.add_reaction(ctx.message, start_emoji)
        await utils.add_reaction(ctx.message, stop_emoji)
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][message.id]['tournament']['round'] = round
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][message.id]['tournament']['trainers'] = trainer_list
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][message.id]['tournament']['next_size'] = 2
        self.bot.guild_dict[ctx.guild.id]['pvp_dict'][message.id]['tournament']['status'] = "active"

    async def bracket_2(self, ctx):
        message = ctx.message
        guild = ctx.guild
        pvp_dict = self.bot.guild_dict[guild.id]['pvp_dict'][message.id]
        embed = message.embeds[0]
        start_emoji = self.bot.custom_emoji.get('pvp_start', u'\U000025b6\U0000fe0f')
        stop_emoji = self.bot.custom_emoji.get('pvp_stop', u'\U000023f9\U0000fe0f')
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
        new_embed.add_field(name=f"**Round {round} Match 1:**", value=f"1\u20e3 {trainer_mentions[1]} **VS** {trainer_mentions[2]} 2\u20e3", inline=False)
        trainer_mentions.remove(None)
        await ctx.message.edit(content=f"PVP Tournament started by {creator.mention}\n\n{creator.mention}, react with the emoji 1\u20e3 through {len(trainer_list)}\u20e3 for each winner of each match!\n\n{creator.mention} can react with {start_emoji} to go to next round once all matches are decided, or react with {stop_emoji} to cancel the tournament.", embed=new_embed)
        await ctx.message.clear_reactions()
        for i in range(2):
            await utils.add_reaction(ctx.message, f'{i+1}\u20e3')
        await utils.add_reaction(ctx.message, start_emoji)
        await utils.add_reaction(ctx.message, stop_emoji)
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
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        error = False
        first = True
        pvp_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/CombatButton.png?cache=1')
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
                    def check(reply):
                        if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                            return True
                        else:
                            return False
                    if not pvp_type or all([pvp_type.lower() != "any", pvp_type.lower() != "great", pvp_type.lower() != "ultra", pvp_type.lower() != "master"]):
                        pvp_embed.add_field(name=_('**New PVP Request**'), value=_("Meowth! I will help you report a PVP battle!\n\nFirst, I'll need to know what **type** of PVP battle you'd like to start. Reply with the **any, great, ultra, or master**. You can reply with **cancel** to stop anytime."), inline=False)
                        pvp_type_wait = await channel.send(embed=pvp_embed)

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
                            first = False
                    if pvp_type != "any":
                        pvp_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/pogo_{pvp_type}_league.png?cache=1")
                    pvp_embed.clear_fields()
                    pvp_embed.add_field(name="**New PVP Request**", value=f"{'Meowth! I will help you report a PVP battle!' if first else ''}\n\n{'First, reply ' if first else 'Great! Now, reply '}with the **location** that you will be at for **{pvp_type} PVP** battles. You can reply with **cancel** to stop anytime.", inline=False)
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
                    pvp_embed.add_field(name="**New PVP Request**", value=f"Fantastic! Now, reply with the **minutes remaining** that you'll be available for **{pvp_type} PVP** battles at {location}. You can reply with **cancel** to stop anytime.", inline=False)
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
            if not message.embeds:
                await utils.safe_delete(message)

    async def _pvp(self, ctx, pvp_type, location, timer):
        dm_dict = {}
        pvp_dict = self.bot.guild_dict[ctx.guild.id].setdefault('pvp_dict', {})
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
        end = now + datetime.timedelta(minutes=int(timer))
        pvp_embed = discord.Embed(colour=ctx.guild.me.colour)
        pvp_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=ctx.author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=ctx.author.avatar_url_as(format=None, static_format='jpg', size=32))
        stop_emoji = self.bot.custom_emoji.get('pvp_stop', u'\U000023f9\U0000fe0f')
        report_emoji = self.bot.custom_emoji.get('pvp_report', u'\U0001F4E2')
        list_emoji = ist_emoji = ctx.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f')
        react_list = [stop_emoji, report_emoji, list_emoji]
        pvp_msg = f"Meowth! PVP Requested by {ctx.author.mention}.\n\nUse {stop_emoji} to cancel, {report_emoji} to report new, or {list_emoji} to list all PVP!"
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
        pvp_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/CombatButton.png")
        pvp_embed.set_author(name=f"PVP Request", icon_url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/CombatButton.png?cache=1")
        if pvp_type != "any":
            pvp_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/pogo_{pvp_type}_league.png")
            pvp_embed.set_author(name=f"{pvp_type.title()} League PVP Request", icon_url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/pogo_{pvp_type}_league.png?cache=1")
        pvp_embed.add_field(name=f"**PVP Type:**", value=pvp_type.title())
        pvp_embed.add_field(name=f"**Available Until:**", value=end.strftime(_('%I:%M %p (%H:%M)')))
        confirmation = await ctx.channel.send(pvp_msg, embed=pvp_embed)
        for reaction in react_list:
            await asyncio.sleep(0.25)
            await utils.add_reaction(confirmation, reaction)
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
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        error = False
        pvp_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/CombatButton.png?cache=1')
        pvp_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        pvp_info = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).get('pvp', {})
        is_moderator = checks.is_mod_check(ctx)
        is_ranked = any([pvp_info.get('leader', []), pvp_info.get('elite', []), pvp_info.get('champion', [])])
        while True:
            def check(reply):
                if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                    return True
                else:
                    return False
            async with ctx.typing():
                if pvp_type and any([pvp_type.lower() == "any", pvp_type.lower() == "great", pvp_type.lower() == "ultra", pvp_type.lower() == "master"]) and location:
                    await self._pvp_tournament(ctx, size, pvp_type, location)
                    return
                else:
                    pvp_embed.add_field(name=_('**New PVP Tournament**'), value=_("Meowth! I'll help you report a PVP Tournament!\n\nFirst, I'll need to know what **size** of PVP tournament you'd like to start. Reply with a currently supported size: **2, 4, 8**. You can reply with **cancel** to stop anytime."), inline=False)
                    pvp_size_wait = await channel.send(embed=pvp_embed)

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
                        pvp_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/pogo_{pvp_type}_league.png?cache=1")
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
                    official_pvp = False
                    if is_moderator or is_ranked:
                        pvp_embed.clear_fields()
                        pvp_embed.add_field(name=_('**New PVP Tournament**'), value=f"Since you are a {'ranked member' if is_ranked else 'moderator'}, I'll need to know if this is an official tournament that will count towards the participants' records. Reply with **yes** or **no**. You can reply with **cancel** to stop anytime.", inline=False)
                        pvp_type_wait = await channel.send(embed=pvp_embed)
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
                        elif any([pvp_type_msg.clean_content.lower() == "yes", pvp_type_msg.clean_content.lower() == "y"]):
                            official_pvp = True
                break
        if not error:
            await self._pvp_tournament(ctx,size,  pvp_type, location, official_pvp)
        else:
            pvp_embed.clear_fields()
            pvp_embed.add_field(name=_('**PVP Tournament Cancelled**'), value=_("Meowth! Your report has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=pvp_embed, delete_after=10)
            await utils.safe_delete(message)

    async def _pvp_tournament(self, ctx, size, pvp_type, location, official_pvp=False):
        dm_dict = {}
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        start_emoji = self.bot.custom_emoji.get('pvp_start', u'\U000025b6\U0000fe0f')
        stop_emoji = self.bot.custom_emoji.get('pvp_stop', u'\U000023f9\U0000fe0f')
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
        pvp_embed = discord.Embed(colour=ctx.guild.me.colour)
        pvp_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=ctx.author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=ctx.author.avatar_url_as(format=None, static_format='jpg', size=32))
        pvp_msg = f"PVP Tournament started by {ctx.author.mention} - React with 1\u20e3 through {size}\u20e3 to join!\n\n{ctx.author.mention} can react with {start_emoji} to start the tournament once {size} trainers have joined, or react with {stop_emoji} to cancel the tournament."
        pvp_embed.title = _('Meowth! Click here for my directions to the PVP!')
        pvp_embed.description = f"Ask {ctx.author.name} if my directions aren't perfect!\n**Location:** {location}"
        loc_url = utils.create_gmaps_query(self.bot, location, ctx.channel, type="pvp")
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        stop_info = ""
        if gym_matching_cog:
            stop_info, location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "pvp", dupe_check=False, autocorrect=False)
            if stop_url:
                loc_url = stop_url
                pvp_embed.description = stop_info
        if not location:
            return
        pvp_embed.url = loc_url
        item = None
        pvp_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/pogo_{pvp_type}_league.png")
        if official_pvp:
            pvp_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/Badge_{pvp_type.title()}.png")
        pvp_embed.set_author(name=f"{pvp_type.title()} League PVP Tournament", icon_url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/pogo_{pvp_type}_league.png?cache=1")
        if official_pvp:
            pvp_embed.set_author(name=f"{pvp_type.title()} League PVP Tournament", icon_url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/Badge_{pvp_type.title()}.png?cache=1")
        pvp_embed.add_field(name=f"**PVP Type:**", value=pvp_type.title())
        pvp_embed.add_field(name=f"**Tournament Size:**", value=str(size))
        confirmation = await ctx.channel.send(pvp_msg, embed=pvp_embed)
        for i in range(int(size)):
            await utils.add_reaction(confirmation, f'{i+1}\u20e3')
        await utils.add_reaction(confirmation, start_emoji)
        await utils.add_reaction(confirmation, stop_emoji)
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
                'official':official_pvp,
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
        """Resets all PVP requests.

        Usage: !pvp reset"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel

        # get settings
        pvp_dict = copy.deepcopy(self.bot.guild_dict[guild.id].setdefault('pvp_dict', {}))
        reset_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/unicode_dash.png?cache=1')
        await utils.safe_delete(message)

        if not pvp_dict:
            return
        if report_message and int(report_message) in pvp_dict.keys():
            try:
                report_message = await channel.fetch_message(report_message)
                await self.expire_pvp(report_message)
            except:
                self.bot.loop.create_task(utils.expire_dm_reports(self.bot, pvp_dict.get(report_message, {}).get('dm_dict', {})))
                del self.bot.guild_dict[guild.id]['pvp_dict'][report_message]
            return
        reset_embed.add_field(name=f"**Reset PVP Requests**", value=f"**Meowth!** Are you sure you\'d like to remove all PVP requests?")
        rusure = await channel.send(embed=reset_embed)
        try:
            timeout = False
            res, reactuser = await utils.ask(self.bot, rusure, author.id)
        except TypeError:
            timeout = True
        if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', u'\U0000274e'):
            await utils.safe_delete(rusure)
            reset_embed.clear_fields()
            reset_embed.add_field(name=f"Reset Cancelled", value=f"Your PVP reset request has been canceled. No changes have been made.")
            return await channel.send(embed=reset_embed, delete_after=10)
        elif res.emoji == self.bot.custom_emoji.get('answer_yes', u'\U00002705'):
            await utils.safe_delete(rusure)
            async with ctx.typing():
                for report in pvp_dict:
                    try:
                        report_message = await channel.fetch_message(report)
                        self.bot.loop.create_task(self.expire_pvp(report))
                    except:
                        self.bot.loop.create_task(utils.expire_dm_reports(self.bot, pvp_dict.get(report, {}).get('dm_dict', {})))
                        del self.bot.guild_dict[guild.id]['pvp_dict'][report]
                reset_embed.clear_fields()
                reset_embed.add_field(name=f"PVPs Reset", value=f"Your reset request has been completed.")
                return await channel.send(embed=reset_embed, delete_after=10)
        else:
            return

    @pvp.command()
    @checks.allowpvpreport()
    async def badge(self, ctx):
        """Adds a badge to a trainer profile.

        Usage: !pvp badge"""
        message = ctx.message
        guild = message.guild
        channel = message.channel
        error = ""
        is_moderator = checks.is_mod_check(ctx)
        if not is_moderator and not self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('pvp', {}).setdefault('leader', []):
            return await utils.safe_delete(cxx.message)
        output = []
        pvp_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/Badge_Master.png?cache=1')
        if is_moderator:
            type_list = self.bot.type_list
        else:
            type_list = list(self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('pvp', {}).setdefault('leader', []))
        for type in self.bot.type_list:
            emoji = utils.parse_emoji(ctx.guild, self.bot.config.type_id_dict[type])
            output.append(f"{emoji} {type.title()}")
        while True:
            def check(reply):
                if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                    return True
                else:
                    return False
            async with ctx.typing():
                pvp_embed.add_field(name=_('**Award PVP Badge**'), value=f"Meowth! I'll help you award a PVP badge!\n\nFirst, I'll need to know what **type** of badge you'd like to award or remove. Reply with a badge **type** or with **cancel** to stop anytime. {'Or reply with **reset** to reset all badges.' if is_moderator else ''}", inline=False)
                pvp_embed.add_field(name=_('**Possible Badges:**'), value=_('{badge_list}').format(badge_list=', '.join(output)), inline=False)
                badge_type_wait = await channel.send(embed=pvp_embed)
                try:
                    badge_type_msg = await self.bot.wait_for('message', timeout=60, check=check)
                except asyncio.TimeoutError:
                    badge_type_msg = None
                await utils.safe_delete(badge_type_wait)
                if not badge_type_msg:
                    error = _("took too long to respond")
                    break
                else:
                    await utils.safe_delete(badge_type_msg)
                if badge_type_msg.clean_content.lower() == "cancel":
                    error = _("cancelled the report")
                    break
                elif badge_type_msg.clean_content.lower() == "reset" and is_moderator:
                    for trainer in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}):
                        if self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].get('pvp', {}).get('badges'):
                            self.bot.guild_dict[ctx.guild.id]['trainers'][trainer]['pvp']['badges'] = []
                    return await ctx.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=f"Removed badges from all users."))
                elif badge_type_msg.clean_content.lower() in self.bot.type_list:
                    badge_type = badge_type_msg.clean_content.lower()
                    badge_emoji = utils.parse_emoji(ctx.guild, self.bot.config.type_id_dict[badge_type])
                else:
                    error = _("entered an invalid type")
                    break
                pvp_embed.clear_fields()
                pvp_embed.add_field(name=_('**Award PVP Badge**'), value=f"Next, I'll need to know what **user** you'd like to add or remove a **{badge_type.title()}** badge for. Reply with a user mention, ID, or case-sensitive username. You can reply with **cancel** to stop anytime.", inline=False)
                user_wait = await channel.send(embed=pvp_embed)
                try:
                    user_msg = await self.bot.wait_for('message', timeout=60, check=check)
                except asyncio.TimeoutError:
                    user_msg = None
                await utils.safe_delete(user_wait)
                if not user_msg:
                    error = _("took too long to respond")
                    break
                else:
                    await utils.safe_delete(user_msg)
                if user_msg.clean_content.lower() == "cancel":
                    error = _("cancelled the report")
                    break
                converter = commands.MemberConverter()
                try:
                    member = await converter.convert(ctx, user_msg.content)
                except:
                    error = _("entered an invalid member")
                    break
                if badge_type in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(member.id, {}).setdefault('pvp', {}).setdefault('badges', []):
                    pvp_embed.clear_fields()
                    pvp_embed.add_field(name=_('**Award PVP Badge**'), value=f"It looks like {member.mention} already has this badge. Would you like to remove it? Reply with **yes** or **no** or with **cancel** to stop anytime.", inline=False)
                    confirm_wait = await channel.send(embed=pvp_embed)
                    try:
                        confirm_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        confirm_msg = None
                    await utils.safe_delete(confirm_wait)
                    if not confirm_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(confirm_msg)
                    if confirm_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif any([confirm_msg.clean_content.lower() == "yes", confirm_msg.clean_content.lower() == "y"]):
                        self.bot.guild_dict[ctx.guild.id]['trainers'][member.id]['pvp']['badges'].remove(badge_type)
                        return await ctx.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=f"Removed {badge_emoji} {badge_type.title()} Badge from {member.mention}"))
                    else:
                        error = _("didn't change anything")
                        break
                break
        if not error:
            self.bot.guild_dict[ctx.guild.id]['trainers'][member.id]['pvp']['badges'].append(badge_type)
            return await ctx.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=f"Awarded {badge_emoji} {badge_type.title()} Badge to {member.mention}"))
        else:
            pvp_embed.clear_fields()
            pvp_embed.add_field(name=_('**Badge Cancelled**'), value=_("Meowth! Your report has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=pvp_embed, delete_after=10)
            await utils.safe_delete(message)

    @pvp.command()
    @checks.allowpvpreport()
    @checks.is_mod()
    async def leader(self, ctx):
        """Manage gym leaders.

        Usage: !pvp leader"""
        message = ctx.message
        guild = message.guild
        channel = message.channel
        error = ""
        output = []
        is_moderator = checks.is_mod_check(ctx)
        pvp_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/Badge_Master.png?cache=1')
        leader_dict = {k:{"emoji":utils.parse_emoji(ctx.guild, self.bot.config.type_id_dict[k]), "leaders":[]} for k in self.bot.type_list}
        for trainer in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}):
            if self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(trainer, {}).setdefault('pvp', {}).setdefault('leader', []):
                for type in self.bot.guild_dict[ctx.guild.id]['trainers'].setdefault(trainer, {}).setdefault('pvp', {}).setdefault('leader', []):
                    user = guild.get_member(trainer)
                    leader_dict[type]['leaders'].append(user)
        for type in leader_dict:
            output.append(f"{leader_dict[type]['emoji']} {type.title()} {'(' if leader_dict[type]['leaders'] else ''}{(', ').join([x.mention for x in leader_dict[type]['leaders']])}{')' if leader_dict[type]['leaders'] else ''}")
        while True:
            def check(reply):
                if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                    return True
                else:
                    return False
            async with ctx.typing():
                pvp_embed.add_field(name=_('**Promote Gym Leader**'), value=f"Meowth! I'll help you promote a user to a gym leader!\n\nFirst, I'll need to know what **type** of leader you'd like to award or remove. Reply with a leader **type** or with **cancel** to stop anytime. {'Or reply with **reset** to reset all leaders.' if is_moderator else ''}", inline=False)
                pvp_embed.add_field(name=_('**Possible Leader Types:**'), value=_('{badge_list}').format(badge_list=', '.join(output)), inline=False)
                badge_type_wait = await channel.send(embed=pvp_embed)
                try:
                    badge_type_msg = await self.bot.wait_for('message', timeout=60, check=check)
                except asyncio.TimeoutError:
                    badge_type_msg = None
                await utils.safe_delete(badge_type_wait)
                if not badge_type_msg:
                    error = _("took too long to respond")
                    break
                else:
                    await utils.safe_delete(badge_type_msg)
                if badge_type_msg.clean_content.lower() == "cancel":
                    error = _("cancelled the report")
                    break
                elif badge_type_msg.clean_content.lower() == "reset" and is_moderator:
                    for trainer in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}):
                        if self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].get('pvp', {}).get('leader'):
                            self.bot.guild_dict[ctx.guild.id]['trainers'][trainer]['pvp']['leader'] = []
                    return await ctx.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=f"Removed all gym leaders."))
                elif badge_type_msg.clean_content.lower() in self.bot.type_list:
                    badge_type = badge_type_msg.clean_content.lower()
                    badge_emoji = utils.parse_emoji(ctx.guild, self.bot.config.type_id_dict[badge_type])
                else:
                    error = _("entered an invalid type")
                    break
                pvp_embed.clear_fields()
                pvp_embed.add_field(name=_('**Promote Gym Leader**'), value=f"Next, I'll need to know what **user** you'd like to add or remove as a {leader_dict[badge_type]['emoji']} **{badge_type.title()}** gym leader. Reply with a user mention, ID, or case-sensitive username. You can reply with **cancel** to stop anytime.", inline=False)
                user_wait = await channel.send(embed=pvp_embed)
                try:
                    user_msg = await self.bot.wait_for('message', timeout=60, check=check)
                except asyncio.TimeoutError:
                    user_msg = None
                await utils.safe_delete(user_wait)
                if not user_msg:
                    error = _("took too long to respond")
                    break
                else:
                    await utils.safe_delete(user_msg)
                if user_msg.clean_content.lower() == "cancel":
                    error = _("cancelled the report")
                    break
                converter = commands.MemberConverter()
                try:
                    member = await converter.convert(ctx, user_msg.content)
                except:
                    error = _("entered an invalid member")
                    break
                if badge_type in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(member.id, {}).setdefault('pvp', {}).setdefault('leader', []):
                    pvp_embed.clear_fields()
                    pvp_embed.add_field(name=_('**Promote Gym Leader**'), value=f"It looks like {member.mention} already is already a leader for that type. Would you like to remove them? Reply with **yes** or **no** or with **cancel** to stop anytime.", inline=False)
                    confirm_wait = await channel.send(embed=pvp_embed)
                    try:
                        confirm_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        confirm_msg = None
                    await utils.safe_delete(confirm_wait)
                    if not confirm_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(confirm_msg)
                    if confirm_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif any([confirm_msg.clean_content.lower() == "yes", confirm_msg.clean_content.lower() == "y"]):
                        self.bot.guild_dict[ctx.guild.id]['trainers'][member.id]['pvp']['leader'].remove(badge_type)
                        return await ctx.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=f"Removed {member.mention} as the {badge_emoji} {badge_type.title()} gym leader"))
                    else:
                        error = _("didn't change anything")
                        break
                break
        if not error:
            for trainer in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}):
                if self.bot.guild_dict[ctx.guild.id]['trainers'].setdefault(trainer, {}).setdefault('pvp', {}).setdefault('leader', []):
                    if badge_type in self.bot.guild_dict[ctx.guild.id]['trainers'].setdefault(trainer, {}).setdefault('pvp', {}).setdefault('leader', []):
                        self.bot.guild_dict[ctx.guild.id]['trainers']['pvp']['leader'].remove(badge_type)
            self.bot.guild_dict[ctx.guild.id]['trainers'][member.id]['pvp']['leader'].append(badge_type)
            if "leader" not in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(member.id, {}).setdefault('pvp', {}).setdefault('record', {}).setdefault('title', []):
                self.bot.guild_dict[ctx.guild.id]['trainers'][member.id]['pvp']['record']['title'].append('leader')
            return await ctx.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=f"Promoted {member.mention} as the {badge_emoji} {badge_type.title()} gym leader"))
        else:
            pvp_embed.clear_fields()
            pvp_embed.add_field(name=_('**Promotion Cancelled**'), value=_("Meowth! Your report has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=pvp_embed, delete_after=10)
            await utils.safe_delete(message)

    @pvp.command()
    @checks.allowpvpreport()
    @checks.is_mod()
    async def elite(self, ctx):
        """Manage Elite Four.

        Usage: !pvp elite"""
        message = ctx.message
        guild = message.guild
        channel = message.channel
        error = ""
        output = []
        elite_emoji = self.bot.config.custom_emoji.get('pvp_elite', u'\U0001F3C6')
        pvp_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/Badge_Master.png?cache=1')
        elite_list = []
        is_moderator = checks.is_mod_check(ctx)
        for trainer in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}):
            if self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(trainer, {}).setdefault('pvp', {}).setdefault('elite', []):
                user = guild.get_member(trainer)
                elite_list.append(user)
        while len(elite_list) < 4:
            elite_list.append(None)
        count = 1
        for item in elite_list:
            output.append(f"{count}) {elite_list[count-1].mention if elite_list[count-1] else 'Unoccupied'}")
            count += 1
        while True:
            def check(reply):
                if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                    return True
                else:
                    return False
            async with ctx.typing():
                pvp_embed.add_field(name=_('**Promote Elite Four**'), value=f"Meowth! I'll help you promote a user to the Elite Four!\n\nFirst, I'll need to know what **slot** of the Elite Four you'd like to fill. Reply with a **number 1-4** or with **cancel** to stop anytime. {'Or reply with **reset** to reset all Elite Four.' if is_moderator else ''}", inline=False)
                pvp_embed.add_field(name=f"Current Elite Four", value=('\n').join(output))
                slot_wait = await channel.send(embed=pvp_embed)
                try:
                    slot_msg = await self.bot.wait_for('message', timeout=60, check=check)
                except asyncio.TimeoutError:
                    slot_msg = None
                await utils.safe_delete(slot_wait)
                if not slot_msg:
                    error = _("took too long to respond")
                    break
                else:
                    await utils.safe_delete(slot_msg)
                if slot_msg.clean_content.lower() == "cancel":
                    error = _("cancelled the report")
                    break
                elif slot_msg.clean_content.lower() == "reset" and is_moderator:
                    for trainer in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}):
                        if self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].get('pvp', {}).get('elite'):
                            self.bot.guild_dict[ctx.guild.id]['trainers'][trainer]['pvp']['elite'] = []
                    return await ctx.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=f"Removed all Elite Four."))
                elif not slot_msg.clean_content.isdigit() or (slot_msg.clean_content.isdigit() and int(slot_msg.clean_content) > 4):
                    error = _("entered something invalid")
                    break
                else:
                    index = int(slot_msg.clean_content) - 1
                    remove_user = elite_list[index]
                pvp_embed.clear_fields()
                pvp_embed.add_field(name=_('**Promote Elite Four**'), value=f"Next, I'll need to know what **user** you'd like to add as an Elite Four member. Reply with a user mention, ID, or case-sensitive username to promote a user{' or reply with **none** to remove '+elite_list[index].mention if elite_list[index] else ''}. You can reply with **cancel** to stop anytime.", inline=False)
                user_wait = await channel.send(embed=pvp_embed)
                try:
                    user_msg = await self.bot.wait_for('message', timeout=60, check=check)
                except asyncio.TimeoutError:
                    user_msg = None
                await utils.safe_delete(user_wait)
                if not user_msg:
                    error = _("took too long to respond")
                    break
                else:
                    await utils.safe_delete(user_msg)
                if user_msg.clean_content.lower() == "cancel":
                    error = _("cancelled the report")
                    break
                elif user_msg.clean_content.lower() == "none":
                    if remove_user:
                        self.bot.guild_dict[ctx.guild.id]['trainers'][remove_user.id]['pvp']['elite'] = False
                        return await ctx.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=f"Remove {remove_user.mention} from the Elite Four!"))
                converter = commands.MemberConverter()
                try:
                    member = await converter.convert(ctx, user_msg.content)
                    self.bot.guild_dict[ctx.guild.id]['trainers'][member.id]['pvp']['elite'] = True
                    if "elite" not in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(member.id, {}).setdefault('pvp', {}).setdefault('record', {}).setdefault('title', []):
                        self.bot.guild_dict[ctx.guild.id]['trainers'][member.id]['pvp']['record']['title'].append('elite')
                    if remove_user:
                        self.bot.guild_dict[ctx.guild.id]['trainers'][remove_user.id]['pvp']['elite'] = False
                except:
                    error = _("entered an invalid member")
                    break
                break
        if not error:
            return await ctx.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=f"Promoted {member.mention} to the {elite_emoji} Elite Four {elite_emoji}"))
        else:
            pvp_embed.clear_fields()
            pvp_embed.add_field(name=_('**Promotion Cancelled**'), value=_("Meowth! Your report has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=pvp_embed, delete_after=10)
            await utils.safe_delete(message)

    @pvp.command()
    @checks.allowpvpreport()
    @checks.is_mod()
    async def champion(self, ctx):
        """Manage league champions.

        Usage: !pvp champion"""
        message = ctx.message
        guild = message.guild
        channel = message.channel
        error = ""
        output = []
        champ_emoji = self.bot.config.custom_emoji.get('pvp_champ', u'\U0001F451')
        is_moderator = checks.is_mod_check(ctx)
        pvp_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/Badge_Master.png?cache=1')
        league_list = ["great", "ultra", "master"]
        leader_dict = {k:[] for k in league_list}
        for trainer in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}):
            if self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(trainer, {}).setdefault('pvp', {}).setdefault('champion', []):
                for type in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(trainer, {}).setdefault('pvp', {}).setdefault('champion', []):
                    user = guild.get_member(trainer)
                    leader_dict[type].append(user)
        for type in leader_dict:
            output.append(f"\U0001F451 {type.title()} League Champion: {(', ').join([x.mention for x in leader_dict[type]]) if leader_dict[type] else 'Unoccupied'}")
        while True:
            def check(reply):
                if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                    return True
                else:
                    return False
            async with ctx.typing():
                pvp_embed.add_field(name=_('**Promote League Champion**'), value=f"Meowth! I'll help you promote a user to league champion!\n\nFirst, I'll need to know what **type** of champion you'd like to award. Reply with a league **type** (great, ultra, master) or with **cancel** to stop anytime. {'Or reply with **reset** to reset all champions.' if is_moderator else ''}", inline=False)
                pvp_embed.add_field(name=_('**Possible Leader Types:**'), value=_('{badge_list}').format(badge_list='\n'.join(output)), inline=False)
                league_type_wait = await channel.send(embed=pvp_embed)
                try:
                    league_type_msg = await self.bot.wait_for('message', timeout=60, check=check)
                except asyncio.TimeoutError:
                    league_type_msg = None
                await utils.safe_delete(league_type_wait)
                if not league_type_msg:
                    error = _("took too long to respond")
                    break
                else:
                    await utils.safe_delete(league_type_msg)
                if league_type_msg.clean_content.lower() == "cancel":
                    error = _("cancelled the report")
                    break
                elif league_type_msg.clean_content.lower() == "reset" and is_moderator:
                    for trainer in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}):
                        if self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].get('pvp', {}).get('champion'):
                            self.bot.guild_dict[ctx.guild.id]['trainers'][trainer]['pvp']['champion'] = []
                    return await ctx.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=f"Removed all champions."))
                elif league_type_msg.clean_content.lower() in league_list:
                    badge_type = league_type_msg.clean_content.lower()
                else:
                    error = _("entered an invalid type")
                    break
                pvp_embed.clear_fields()
                pvp_embed.add_field(name=_('**Promote Champion**'), value=f"Next, I'll need to know what **user** you'd like to add or remove as the **{badge_type.title()}** league champion. Reply with a user mention, ID, or case-sensitive username. You can reply with **cancel** to stop anytime.", inline=False)
                user_wait = await channel.send(embed=pvp_embed)
                try:
                    user_msg = await self.bot.wait_for('message', timeout=60, check=check)
                except asyncio.TimeoutError:
                    user_msg = None
                await utils.safe_delete(user_wait)
                if not user_msg:
                    error = _("took too long to respond")
                    break
                else:
                    await utils.safe_delete(user_msg)
                if user_msg.clean_content.lower() == "cancel":
                    error = _("cancelled the report")
                    break
                converter = commands.MemberConverter()
                try:
                    member = await converter.convert(ctx, user_msg.content)
                except:
                    error = _("entered an invalid member")
                    break
                if badge_type in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(member.id, {}).setdefault('pvp', {}).setdefault('champion', []):
                    pvp_embed.clear_fields()
                    pvp_embed.add_field(name=_('**Promote Champion**'), value=f"It looks like {member.mention} already is the {badge_type} champion. Would you like to remove them? Reply with **yes** or **no** or with **cancel** to stop anytime.", inline=False)
                    confirm_wait = await channel.send(embed=pvp_embed)
                    try:
                        confirm_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        confirm_msg = None
                    await utils.safe_delete(confirm_wait)
                    if not confirm_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(confirm_msg)
                    if confirm_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif any([confirm_msg.clean_content.lower() == "yes", confirm_msg.clean_content.lower() == "y"]):
                        self.bot.guild_dict[ctx.guild.id]['trainers'][member.id]['pvp']['champion'].remove(badge_type)
                        return await ctx.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=f"Removed {member.mention} as the {badge_type.title()} league champion"))
                    else:
                        error = _("didn't change anything")
                        break
                break
        if not error:
            for trainer in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}):
                if self.bot.guild_dict[ctx.guild.id]['trainers'].setdefault(trainer, {}).setdefault('pvp', {}).setdefault('champion', []):
                    if badge_type in self.bot.guild_dict[ctx.guild.id]['trainers'].setdefault(trainer, {}).setdefault('pvp', {}).setdefault('champion', []):
                        self.bot.guild_dict[ctx.guild.id]['trainers']['pvp']['champion'].remove(badge_type)
            self.bot.guild_dict[ctx.guild.id]['trainers'][member.id]['pvp']['champion'].append(badge_type)
            if "champion" not in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(member.id, {}).setdefault('pvp', {}).setdefault('record', {}).setdefault('title', []):
                self.bot.guild_dict[ctx.guild.id]['trainers'][member.id]['pvp']['record']['title'].append('champion')
            return await ctx.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=f"Promoted {member.mention} as the {champ_emoji} {badge_type.title()} League Champion {champ_emoji}"))
        else:
            pvp_embed.clear_fields()
            pvp_embed.add_field(name=_('**Promotion Cancelled**'), value=_("Meowth! Your report has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=pvp_embed, delete_after=10)
            await utils.safe_delete(message)

    @pvp.command()
    @checks.allowpvpreport()
    @checks.is_mod()
    async def record(self, ctx):
        """Manage league records.

        Usage: !pvp record"""
        message = ctx.message
        guild = message.guild
        channel = message.channel
        error = ""
        is_moderator = checks.is_mod_check(ctx)
        pvp_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/CombatButton.png?cache=1')
        while True:
            def check(reply):
                if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                    return True
                else:
                    return False
            async with ctx.typing():
                pvp_embed.add_field(name=_('**Manage League Records**'), value=f"Meowth! I'll help you manage your league records. First, I'll need to know what **user** you'd like to modify. Reply with a user mention, ID, or case-sensitive username. You can reply with **cancel** to stop anytime, **reset** to reset all win-loss records, or **wipe** to remove all win-loss records as well as previously held titles.", inline=False)
                user_wait = await channel.send(embed=pvp_embed)
                try:
                    user_msg = await self.bot.wait_for('message', timeout=60, check=check)
                except asyncio.TimeoutError:
                    user_msg = None
                await utils.safe_delete(user_wait)
                if not user_msg:
                    error = _("took too long to respond")
                    break
                else:
                    await utils.safe_delete(user_msg)
                if user_msg.clean_content.lower() == "cancel":
                    error = _("cancelled the report")
                    break
                elif (user_msg.clean_content.lower() == "reset" or user_msg.clean_content.lower() == "wipe") and is_moderator:
                    for trainer in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}):
                        if self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].setdefault('pvp', {}).get('record', {}).get('win', 0):
                            self.bot.guild_dict[ctx.guild.id]['trainers'][trainer]['pvp']['record']['win'] = 0
                            self.bot.guild_dict[ctx.guild.id]['trainers'][trainer]['pvp']['record']['loss'] = 0
                        if self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].setdefault('pvp', {}).get('record', {}).get('title', []) and user_msg.clean_content.lower() == "wipe":
                            self.bot.guild_dict[ctx.guild.id]['trainers'][trainer]['pvp']['record']['title'] = []
                    return await ctx.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=f"Reset all records."))
                converter = commands.MemberConverter()
                try:
                    member = await converter.convert(ctx, user_msg.content)
                except:
                    error = _("entered an invalid member")
                    break
                pvp_embed.clear_fields()
                pvp_embed.add_field(name=_('**Manage League Records**'), value=f"Next, I'll need to know what **stat** you'd like to edit. Reply with **win** or **loss**. You can reply with **cancel** to stop anytime.", inline=False)
                user_wait = await channel.send(embed=pvp_embed)
                try:
                    user_msg = await self.bot.wait_for('message', timeout=60, check=check)
                except asyncio.TimeoutError:
                    user_msg = None
                await utils.safe_delete(user_wait)
                if not user_msg:
                    error = _("took too long to respond")
                    break
                else:
                    await utils.safe_delete(user_msg)
                if user_msg.clean_content.lower() == "cancel":
                    error = _("cancelled the report")
                    break
                elif user_msg.clean_content.lower() == "win":
                    pvp_embed.clear_fields()
                    pvp_embed.add_field(name=_('**Manage League Records**'), value=f"Now, enter the number of wins for {member.mention}. You can reply with **cancel** to stop anytime.", inline=False)
                    user_wait = await channel.send(embed=pvp_embed)
                    try:
                        user_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        user_msg = None
                    await utils.safe_delete(user_wait)
                    if not user_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(user_msg)
                    if user_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif not user_msg.clean_content.isdigit():
                        error = _("entered an invalid number")
                        break
                    else:
                        pvp_info = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(member.id, {}).setdefault('pvp', {}).setdefault('record', {})
                        pvp_info['win'] = int(user_msg.clean_content)
                        return await ctx.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=f"Manually set win record for {member.mention} to {user_msg.clean_content}."))
                elif user_msg.clean_content.lower() == "loss":
                    pvp_embed.clear_fields()
                    pvp_embed.add_field(name=_('**Manage League Records**'), value=f"Now, enter the number losses wins for {member.mention}. You can reply with **cancel** to stop anytime.", inline=False)
                    user_wait = await channel.send(embed=pvp_embed)
                    try:
                        user_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        user_msg = None
                    await utils.safe_delete(user_wait)
                    if not user_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(user_msg)
                    if user_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif not user_msg.clean_content.isdigit():
                        error = _("entered an invalid number")
                        break
                    else:
                        pvp_info = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(member.id, {}).setdefault('pvp', {}).setdefault('record', {})
                        pvp_info['loss'] = int(user_msg.clean_content)
                        return await ctx.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=f"Manually set loss record for {member.mention} to {user_msg.clean_content}."))
                elif user_msg.clean_content.lower() == "title":
                    pvp_embed.clear_fields()
                    pvp_embed.add_field(name=_('**Manage League Records**'), value=f"Now, enter the titles to attach to {member.mention}. This is to track whether {member.mention} has ever held these titles in your current season or career, not whether they are currently held. Reply with a comma-separated list of any of the following: **leader, elite, champion**. You can reply with **cancel** to stop anytime.", inline=False)
                    title_list = ["leader", "elite", "champion"]
                    user_wait = await channel.send(embed=pvp_embed)
                    try:
                        user_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        user_msg = None
                    await utils.safe_delete(user_wait)
                    if not user_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(user_msg)
                    if user_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    else:
                        title_split = user_msg.clean_content.lower().split(',')
                        title_split = [x.strip() for x in title_split]
                        titie_split = [x for x in title_split if x in title_list]
                        pvp_info = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(member.id, {}).setdefault('pvp', {}).setdefault('record', {})
                        pvp_info['title'] = title_split
                        return await ctx.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=f"Manually set titles for {member.mention} to {(', ').join(title_split)}."))
                break
        if not error:
            for trainer in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}):
                if self.bot.guild_dict[ctx.guild.id]['trainers'].setdefault(trainer, {}).setdefault('pvp', {}).setdefault('champion', []):
                    if badge_type in self.bot.guild_dict[ctx.guild.id]['trainers'].setdefault(trainer, {}).setdefault('pvp', {}).setdefault('champion', []):
                        self.bot.guild_dict[ctx.guild.id]['trainers']['pvp']['champion'].remove(badge_type)
            self.bot.guild_dict[ctx.guild.id]['trainers'][member.id]['pvp']['champion'].append(badge_type)
            return await ctx.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=f"Promoted {member.mention} as the {badge_type.title()} league champion"))
        else:
            pvp_embed.clear_fields()
            pvp_embed.add_field(name=_('**Management Cancelled**'), value=_("Meowth! Your report has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=pvp_embed, delete_after=10)
            await utils.safe_delete(message)

def setup(bot):
    bot.add_cog(Pvp(bot))

def teardown(bot):
    bot.remove_cog(Pvp)
