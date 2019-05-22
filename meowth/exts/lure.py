import asyncio
import copy
import re
import time
import datetime
import dateparser
import textwrap
import logging
import string

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
        while True:
            logger.info('------ BEGIN ------')
            guilddict_temp = copy.deepcopy(self.bot.guild_dict)
            expire_list = []
            count = 0
            for guildid in guilddict_temp.keys():
                lure_dict = guilddict_temp[guildid].setdefault('lure_dict', {})
                for reportid in lure_dict.keys():
                    if lure_dict[reportid].get('exp', 0) <= time.time():
                        report_channel = self.bot.get_channel(lure_dict[reportid].get('reportchannel'))
                        if report_channel:
                            try:
                                report_message = await report_channel.fetch_message(reportid)
                                self.bot.loop.create_task(self.expire_lure(report_message))
                                count += 1
                                continue
                            except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                                pass
                        try:
                            del self.bot.guild_dict[guildid]['wildreport_dict'][reportid]
                        except KeyError:
                            continue
                    to_expire = lure_dict[reportid].get('exp', 0) - time.time()
                    expire_list.append(to_expire)
            # save server_dict changes after cleanup
            logger.info('SAVING CHANGES')
            try:
                await self.bot.save()
            except Exception as err:
                logger.info('SAVING FAILED' + err)
                pass
            if not expire_list:
                expire_list = [600]
            logger.info(f"------ END - {count} Wilds Cleaned - Waiting {min(expire_list)} seconds. ------")
            if not loop:
                return
            await asyncio.sleep(min(expire_list))
            continue

    @lure_cleanup.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    async def expire_lure(self, message):
        guild = message.channel.guild
        channel = message.channel
        lure_dict = copy.deepcopy(self.bot.guild_dict[guild.id]['questreport_dict'])
        await utils.safe_delete(message)
        try:
            user_message = await channel.fetch_message(lure_dict[message.id]['reportmessage'])
            await utils.safe_delete(user_message)
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, KeyError):
            pass
        await utils.expire_dm_reports(self.bot, lure_dict.get(message.id, {}).get('dm_dict', {}))
        try:
            del self.bot.guild_dict[guild.id]['questreport_dict'][message.id]
        except KeyError:
            pass

    @commands.command()
    @checks.allowlurereport()
    async def lure(self, ctx, lure_type=None, *, location:commands.clean_content(fix_channel_mentions=True)="", timer="30"):
        """Report an ongoing lure.

        Usage: !lure [type] [pokestop] [minutes]
        Guided report available with just !lure"""
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset']))
        error = False
        lure_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey.png?cache=1')
        lure_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        while True:
            async with ctx.typing():
                if lure_type and any([lure_type.lower() == "normal", lure_type.lower() == "moss", lure_type.lower() == "glacial", lure_type.lower() == "magnetic"]) and location:
                    if location.split()[-1].isdigit():
                        timer = location.split()[-1]
                        location = location.replace(timer, '').strip()
                    await self._lure(ctx, lure_type, location, timer)
                    return
                else:
                    lure_embed.add_field(name=_('**New Lure Report**'), value=_("Meowth! I'll help you report a lure!\n\nFirst, I'll need to know what **type** the lure is. Reply with the **normal, moss, magnetic, or glacial**. You can reply with **cancel** to stop anytime."), inline=False)
                    lure_type_wait = await channel.send(embed=lure_embed)
                    def check(reply):
                        if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                            return True
                        else:
                            return False
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
                    elif not any([lure_type_msg.clean_content.lower() == "normal", lure_type_msg.clean_content.lower() == "moss", lure_type_msg.clean_content.lower() == "magnetic", lure_type_msg.clean_content.lower() == "glacial"]):
                        error = _("entered an invalid type")
                        break
                    else:
                        lure_type = lure_type_msg.clean_content.lower()
                        if lure_type != "normal":
                            lure_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey_{lure_type}.png?cache=1")
                    lure_embed.clear_fields()
                    lure_embed.add_field(name="**New Lure Report**", value=f"Great! Now, reply with the **pokestop** that has the **{lure_type} lure** raid. You can reply with **cancel** to stop anytime.", inline=False)
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
                        gym_matching_cog = self.bot.cogs.get('GymMatching')
                        stop_info = ""
                        if gym_matching_cog:
                            stop_info, location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "lure", dupe_check=False)
                            if stop_url:
                                loc_url = stop_url
                        if not location:
                            return
                    lure_embed.clear_fields()
                    lure_embed.add_field(name="**New Lure Report**", value=f"Fantastic! Now, reply with the **minutes remaining** before the **{lure_type} lure** ends. This is usually 30 minutes from when the lure started unless there is an event. You can reply with **cancel** to stop anytime.", inline=False)
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
                    elif expire_msg:
                        timer = expire_msg.clean_content
                    lure_embed.remove_field(0)
                    break
        if not error:
            await self._lure(ctx, lure_type, location, timer)
        else:
            lure_embed.clear_fields()
            lure_embed.add_field(name=_('**Lure Report Cancelled**'), value=_("Meowth! Your report has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=lure_embed, delete_after=10)
            await utils.safe_delete(message)

    async def _lure(self, ctx, lure_type, location, timer):
        dm_dict = {}
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.message.channel.guild.id]['configure_dict']['settings']['offset']))
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['offset'])
        end = now + datetime.timedelta(minutes=int(timer))
        lure_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey.png?cache=1')
        lure_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=ctx.author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=ctx.author.avatar_url_as(format=None, static_format='jpg', size=32))
        lure_msg = _("Lure reported by {author}").format(author=ctx.author.mention)
        lure_embed.title = _('Meowth! Click here for my directions to the lure!')
        lure_embed.description = _("Ask {author} if my directions aren't perfect!").format(author=ctx.author.name)
        loc_url = utils.create_gmaps_query(self.bot, location, ctx.channel, type="lure")
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        stop_info = ""
        if gym_matching_cog:
            stop_info, location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "lure", dupe_check=False)
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
        if lure_type == "glacial":
            lure_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey_glacial.png")
            lure_embed.set_author(name=f"Glacial Lure Report", icon_url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey_glacial.png?cache=1")
            item = "glacial lure module"
        elif lure_type == "magnetic":
            lure_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey_magnetic.png")
            lure_embed.set_author(name=f"Magnetic Lure Report", icon_url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey_magnetic.png?cache=1")
            item = "magnetic lure module"
        elif lure_type == "moss":
            lure_embed.set_thumbnail(url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey_moss.png")
            lure_embed.set_author(name=f"Mossy Lure Report", icon_url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/TroyKey_moss.png?cache=1")
            item = "mossy lure module"
        lure_embed.add_field(name=f"Lure Type", value=item.title())
        lure_embed.add_field(name=f"Expires", value=end.strftime(_('%I:%M %p (%H:%M)')))
        confirmation = await ctx.channel.send(lure_msg, embed=lure_embed)
        test_var = self.bot.guild_dict[ctx.guild.id].setdefault('lure_dict', {}).setdefault(confirmation.id, {})
        self.bot.guild_dict[ctx.guild.id]['lure_dict'][confirmation.id] = {
            'exp':time.time() + int(timer)*60,
            'expedit':"delete",
            'reportmessage':ctx.message.id,
            'reportchannel':ctx.channel.id,
            'reportauthor':ctx.author.id,
            'dm_dict':dm_dict,
            'location':location,
            'url':loc_url,
            'type':lure_type
        }
        lure_embed.description = lure_embed.description + f"\n**Report:** [Jump to Message]({confirmation.jump_url})"
        for trainer in self.bot.guild_dict[ctx.guild.id].get('trainers', {}):
            user_stops = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('stops', [])
            user_items = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('items', [])
            if not checks.dm_check(ctx, trainer):
                continue
            if location.lower() in user_stops or item in user_items:
                try:
                    user = ctx.guild.get_member(trainer)
                    luredmmsg = await user.send(f"{lure_msg} in {ctx.channel.mention}", embed=lure_embed)
                    dm_dict[user.id] = luredmmsg.id
                except:
                    continue
        self.bot.guild_dict[ctx.guild.id]['lure_dict'][confirmation.id]['dm_dict'] = dm_dict

def setup(bot):
    bot.add_cog(Lure(bot))
