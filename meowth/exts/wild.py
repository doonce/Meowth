import asyncio
import copy
import re
import time
import datetime
import dateparser
import textwrap
import logging
import traceback

import discord
from discord.ext import commands, tasks

from meowth import checks
from meowth.exts import pokemon as pkmn_class
from meowth.exts import utilities as utils

logger = logging.getLogger("meowth")

class Wild(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.wild_cleanup.start()

    def cog_unload(self):
        self.wild_cleanup.cancel()

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
        try:
            wildreport_dict = self.bot.guild_dict[guild.id].setdefault('wildreport_dict', {})
        except KeyError:
            wildreport_dict = {}
        if message.id in wildreport_dict:
            wild_dict = self.bot.guild_dict[guild.id]['wildreport_dict'][message.id]
            if str(payload.emoji) == self.bot.custom_emoji.get('wild_omw', u'\U0001F3CE\U0000fe0f'):
                wild_dict['omw'].append(user.mention)
                self.bot.guild_dict[guild.id]['wildreport_dict'][message.id] = wild_dict
            elif str(payload.emoji) == self.bot.custom_emoji.get('wild_despawn', u'\U0001F4A8'):
                for reaction in message.reactions:
                    if reaction.emoji == self.bot.custom_emoji.get('wild_despawn', u'\U0001F4A8') and (reaction.count >= 3 or can_manage):
                        if wild_dict['omw']:
                            despawn = _("has despawned")
                            await channel.send(f"{', '.join(wild_dict['omw'])}: {wild_dict['pokemon'].title()} {despawn}!")
                        await self.expire_wild(message)
            elif str(payload.emoji) == self.bot.custom_emoji.get('wild_catch', u'\U000026be'):
                if user.id not in wild_dict.get('caught_by', []):
                    if user.id != wild_dict['report_author']:
                        wild_dict.get('caught_by', []).append(user.id)
                    if user.mention in wild_dict['omw']:
                        wild_dict['omw'].remove(user.mention)
                        await message.remove_reaction(self.bot.custom_emoji.get('wild_omw', u'\U0001F3CE\U0000fe0f'), user)
            elif str(payload.emoji) == self.bot.custom_emoji.get('wild_info', u'\U00002139\U0000fe0f'):
                ctx = await self.bot.get_context(message)
                if not ctx.prefix:
                    prefix = self.bot._get_prefix(self.bot, message)
                    ctx.prefix = prefix[-1]
                await message.remove_reaction(payload.emoji, user)
                ctx.author = user
                await self.add_wild_info(ctx, message)
            elif str(payload.emoji) == self.bot.custom_emoji.get('wild_report', u'\U0001F4E2'):
                ctx = await self.bot.get_context(message)
                ctx.author, ctx.message.author = user, user
                await message.remove_reaction(payload.emoji, user)
                return await ctx.invoke(self.bot.get_command('wild'))
            elif str(payload.emoji) == self.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f'):
                ctx = await self.bot.get_context(message)
                await asyncio.sleep(0.25)
                await message.remove_reaction(payload.emoji, self.bot.user)
                await asyncio.sleep(0.25)
                await message.remove_reaction(payload.emoji, user)
                await ctx.invoke(self.bot.get_command("list wild"))
                await asyncio.sleep(5)
                await utils.safe_reaction(message, payload.emoji)

    @tasks.loop(seconds=10)
    async def wild_cleanup(self, loop=True):
        logger.info('------ BEGIN ------')
        despawn_list = []
        count = 0
        for guild in list(self.bot.guilds):
            if guild.id not in list(self.bot.guild_dict.keys()):
                continue
            try:
                wild_dict = self.bot.guild_dict[guild.id].setdefault('wildreport_dict', {})
                for reportid in list(wild_dict.keys()):
                    if wild_dict.get(reportid, {}).get('exp', 0) <= time.time():
                        report_channel = self.bot.get_channel(wild_dict.get(reportid, {}).get('report_channel'))
                        if report_channel:
                            try:
                                report_message = await report_channel.fetch_message(reportid)
                                self.bot.loop.create_task(self.expire_wild(report_message))
                                count += 1
                                continue
                            except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                                pass
                        try:
                            self.bot.loop.create_task(utils.expire_dm_reports(self.bot, wild_dict.get(reportid, {}).get('dm_dict', {})))
                            del self.bot.guild_dict[guild.id]['wildreport_dict'][reportid]
                            count += 1
                            continue
                        except KeyError:
                            continue
                    to_despawn = wild_dict.get(reportid, {}).get('exp', 0) - time.time()
                    if to_despawn > 10:
                        despawn_list.append(to_despawn)
            except Exception as e:
                print(traceback.format_exc())
        # save server_dict changes after cleanup
        logger.info('SAVING CHANGES')
        try:
            await self.bot.save
        except Exception as err:
            logger.info('SAVING FAILED' + str(err))
        if not despawn_list:
            despawn_list = [300]
        logger.info(f"------ END - {count} Wilds Cleaned - Waiting {min(despawn_list)} seconds. ------")
        if not loop:
            return
        self.wild_cleanup.change_interval(seconds=min(despawn_list))

    @wild_cleanup.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    async def expire_wild(self, message):
        guild = message.channel.guild
        channel = message.channel
        wild_dict = copy.deepcopy(self.bot.guild_dict[guild.id]['wildreport_dict'])
        author = guild.get_member(wild_dict.get(message.id, {}).get('report_author'))
        try:
            await message.edit(content=message.content.splitlines()[0], embed=discord.Embed(description=wild_dict[message.id]['expedit']['embedcontent'], colour=message.embeds[0].colour.value))
            await message.clear_reactions()
        except (discord.errors.NotFound, discord.errors.Forbidden, KeyError):
            pass
        try:
            user_message = await channel.fetch_message(wild_dict[message.id]['report_message'])
            await utils.safe_delete(user_message)
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, KeyError):
            pass
        await utils.expire_dm_reports(self.bot, wild_dict.get(message.id, {}).get('dm_dict', {}))
        wild_bonus = self.bot.guild_dict[guild.id]['wildreport_dict'].get(message.id, {}).get('caught_by', [])
        if len(wild_bonus) >= 3 and author and not author.bot:
            wild_reports = self.bot.guild_dict[message.guild.id].setdefault('trainers', {}).setdefault(author.id, {}).setdefault('reports', {}).setdefault('wild', 0) + 1
            self.bot.guild_dict[message.guild.id]['trainers'][author.id]['reports']['wild'] = wild_reports
        try:
            del self.bot.guild_dict[guild.id]['wildreport_dict'][message.id]
        except KeyError:
            pass

    async def make_wild_embed(self, ctx, details):
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))).strftime(_('%I:%M %p (%H:%M)'))
        gender = details.get('gender', None)
        gender = gender if gender else ''
        wild_iv = details.get('wild_iv', {})
        iv_percent = wild_iv.get('percent', None)
        iv_percent = "0" if iv_percent == 0 else iv_percent
        iv_atk = wild_iv.get('iv_atk')
        iv_atk = "X" if not iv_atk else iv_atk
        iv_def = wild_iv.get('iv_def')
        iv_def = "X" if not iv_def else iv_def
        iv_sta = wild_iv.get('iv_sta')
        iv_sta = "X" if not iv_sta else iv_sta
        iv_long = None
        if iv_atk != "X" or iv_def != "X" or iv_sta != "X":
            iv_long = f"{iv_atk} / {iv_def} / {iv_sta}"
        level = details.get('level', None)
        cp = details.get('cp', None)
        weather = details.get('weather', None)
        height = details.get('height', None)
        weight = details.get('weight', None)
        moveset = details.get('moveset', None)
        expire = details.get('expire', "45 min 0 sec")
        pkmn_obj = details.get('pkmn_obj', None)
        disguise = details.get('disguise', None)
        if disguise:
            disguise = await pkmn_class.Pokemon.async_get_pokemon(self.bot, disguise)
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, f"{gender.lower()} {pkmn_obj.lower()}")
        pokemon.weather = weather
        location = details.get('location', None)
        wild_gmaps_link = utils.create_gmaps_query(self.bot, location, ctx.channel, type="wild")
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        poi_info = ""
        nearest_stop = ""
        if gym_matching_cog:
            poi_info, location, poi_url = await gym_matching_cog.get_poi_info(ctx, location, "wild", autocorrect=False)
            if poi_url:
                wild_gmaps_link = poi_url
                wild_coordinates = poi_url.split("query=")[1]
                nearest_stop = await gym_matching_cog.find_nearest_stop((wild_coordinates.split(",")[0],wild_coordinates.split(",")[1]), ctx.guild.id)
        if details.get('coordinates'):
            wild_gmaps_link = "https://www.google.com/maps/search/?api=1&query={0}".format(details['coordinates'])
        huntrexpstamp = (ctx.message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0), minutes=int(expire.split()[0]), seconds=int(expire.split()[2]))).strftime('%I:%M %p')
        shiny_str = ""
        if pokemon.id in self.bot.shiny_dict:
            if str(pokemon.form).lower() in self.bot.shiny_dict.get(pokemon.id, {}) and "wild" in self.bot.shiny_dict.get(pokemon.id, {}).get(str(pokemon.form).lower(), []):
                shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
        details_str = f"{shiny_str}{pokemon.name.title()}"
        if gender and "female" in gender.lower():
            details_str += f" ♀"
        elif gender and "male" in gender.lower():
            details_str += f" ♂"
        details_str += f" {pokemon.emoji}"
        if pokemon.name.lower() == "ditto" and disguise:
            details_str += f"\nDisguise: {disguise.name.title()} {disguise.emoji}"
        wild_embed = discord.Embed(description="", title=_('Meowth! Click here for exact directions to the wild {pokemon}!').format(pokemon=pokemon.name.title()), url=wild_gmaps_link, colour=ctx.guild.me.colour)
        if nearest_stop:
            wild_embed.description = poi_info
        wild_embed.add_field(name=_('**Details:**'), value=details_str, inline=True)
        if iv_long or iv_percent or level or cp or pokemon.is_boosted:
            wild_embed.add_field(name=f"**IV{' / Level' if level or cp or pokemon.is_boosted else ''}:**", value=f"{iv_long if iv_long else ''}{' (' if iv_long and iv_percent else ''}{str(iv_percent)+'%' if iv_percent else ''}{')' if iv_long and iv_percent else ''}\n{'Level '+str(level) if level else ''}{' ('+str(cp)+'CP)' if cp else ''} {pokemon.is_boosted if pokemon.is_boosted else ''}", inline=True)
        if height or weight or moveset:
            wild_embed.add_field(name=_('**Other Info:**'), value=f"{'H: '+height if height else ''} {'W: '+weight if weight else ''}\n{moveset if moveset else ''}", inline=True)
        elif iv_long or iv_percent or level or cp or pokemon.is_boosted:
            wild_embed.add_field(name=_('**Other Info (Base):**'), value=f"H: {round(pokemon.height, 2) if pokemon.height else 'X'}m W: {round(pokemon.weight, 2) if pokemon.weight else 'X'}kg\n{ctx.prefix}dex stats {str(pokemon).lower()}", inline=True)
        wild_embed.add_field(name=f"{'**Est. Despawn:**' if int(expire.split()[0]) == 45 and int(expire.split()[2]) == 0 else '**Despawns in:**'}", value=_('{huntrexp} mins ({huntrexpstamp})').format(huntrexp=expire.split()[0], huntrexpstamp=huntrexpstamp), inline=True)
        wild_embed.set_thumbnail(url=pokemon.img_url)
        wild_embed.set_author(name=f"Wild {pokemon.name.title()} Report", icon_url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_grass.png?cache=1")
        wild_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=ctx.author.display_name, timestamp=timestamp), icon_url=ctx.author.avatar_url_as(format=None, static_format='jpg', size=32))
        return wild_embed

    async def add_wild_info(self, ctx, message):
        wild_dict = self.bot.guild_dict[ctx.guild.id]['wildreport_dict'].get(message.id, {})
        message = ctx.message
        channel = message.channel
        guild = message.guild
        author = guild.get_member(wild_dict.get('report_author', None))
        location = wild_dict.get('location', '')
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, wild_dict.get('pkmn_obj', None))
        if not author:
            return
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        error = False
        success = []
        reply_msg = f"**iv <pokemon iv percentage>** - Current: {wild_dict.get('wild_iv', {}).get('percent', 'X')}\n"
        reply_msg += f"**attack <pokemon attack stat>** - Current: {wild_dict.get('wild_iv', {}).get('iv_atk', 'X')}\n"
        reply_msg += f"**defense <pokemon defense stat>** - Current: {wild_dict.get('wild_iv', {}).get('iv_def', 'X')}\n"
        reply_msg += f"**stamina <pokemon stamina stat>** - Current: {wild_dict.get('wild_iv', {}).get('iv_sta', 'X')}\n"
        reply_msg += f"**level <pokemon level>** - Current: {wild_dict.get('level', 'X')}\n"
        reply_msg += f"**cp <pokemon cp>** - Current: {wild_dict.get('cp', 'X')}\n"
        reply_msg += f"**gender <male or female>** - Current: {wild_dict.get('gender', 'X')}\n"
        reply_msg += f"**size <xl or xs>** - Current: {wild_dict.get('size', 'X')}\n"
        reply_msg += f"**weather <game weather>** - Current: {wild_dict.get('weather', 'X')}"
        if pokemon.name.lower() == "ditto":
            reply_msg += f"\n**disguise <ditto disguise>** - Current: {wild_dict.get('disguise', 'X')}"
        wild_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/trade_tut_strength_adjust.png?cache=1')
        wild_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        while True:
            async with ctx.typing():
                wild_embed.add_field(name=_('**Edit Wild Info**'), value=f"Meowth! I'll help you add information to the wild **{str(pokemon)}** near **{location}**!\n**NOTE:** Please make sure you are at least level 30 before setting IV, level, and CP.\n\nI'll need to know what **values** you'd like to edit. Reply **cancel** to stop anytime or reply with a comma separated list of the following options `Ex: iv 100, level 30, weather none`:\n\n{reply_msg}", inline=False)
                value_wait = await channel.send(embed=wild_embed)
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
                        if "cp" in value and "cp" not in success:
                            if value_split[1] and value_split[1].isdigit() and int(value_split[1]) < 5000:
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['cp'] = int(value_split[1])
                                success.append("cp")
                            elif value_split[1] and value_split[1].lower() == "none":
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['cp'] = None
                                success.append("cp")
                            else:
                                error = _('entered something invalid. CPs can\'t be higher than 5000')
                        elif "gender" in value and "gender" not in success:
                            if value_split[1] and (value_split[1] == "male" or value_split[1] == "female"):
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['gender'] = value_split[1]
                                success.append("gender")
                            elif value_split[1] and value_split[1].lower() == "none":
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['gender'] = None
                                success.append("gender")
                            else:
                                error = _('entered something invalid. Please enter male or female')
                        elif "size" in value and "size" not in success:
                            if value_split[1] and (value_split[1] == "xl" or value_split[1] == "xs"):
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['size'] = value_split[1].upper()
                                success.append("size")
                            elif value_split[1] and value_split[1].lower() == "none":
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['size'] = None
                                success.append("size")
                            else:
                                error = _('entered something invalid. Please enter male or female')
                        elif "iv" in value and "iv" not in success:
                            if value_split[1] and value_split[1].isdigit() and int(value_split[1]) <= 100:
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['wild_iv']['percent'] = int(value_split[1])
                                success.append("iv")
                            elif value_split[1] and value_split[1].lower() == "none":
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['wild_iv']['percent'] = None
                                success.append("iv")
                            else:
                                error = _('entered something invalid. IVs can\'t be higher than 100')
                        elif "attack" in value and "attack" not in success:
                            if value_split[1] and value_split[1].isdigit() and int(value_split[1]) <= 15:
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['wild_iv']['iv_atk'] = int(value_split[1])
                                success.append("attack")
                            elif value_split[1] and value_split[1].lower() == "none":
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['wild_iv']['iv_atk'] = None
                                success.append("attack")
                            else:
                                error = _('entered something invalid. Stats can\'t be higher than 15')
                        elif "defense" in value and "defense" not in success:
                            if value_split[1] and value_split[1].isdigit() and int(value_split[1]) <= 15:
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['wild_iv']['iv_def'] = int(value_split[1])
                                success.append("defense")
                            elif value_split[1] and value_split[1].lower() == "none":
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['wild_iv']['iv_def'] = None
                                success.append("defense")
                            else:
                                error = _('entered something invalid. Stats can\'t be higher than 15')
                        elif "stamina" in value and "sstamina" not in success:
                            if value_split[1] and value_split[1].isdigit() and int(value_split[1]) <= 15:
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['wild_iv']['iv_sta'] = int(value_split[1])
                                success.append("stamina")
                            elif value_split[1] and value_split[1].lower() == "none":
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['wild_iv']['iv_sta'] = None
                                success.append("stamina")
                            else:
                                error = _('entered something invalid. Stats can\'t be higher than 15')
                        elif "level" in value and "level" not in success:
                            if value_split[1] and value_split[1].isdigit() and int(value_split[1]) <= 40:
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['level'] = int(value_split[1])
                                success.append("level")
                            elif value_split[1] and value_split[1].lower() == "none":
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['level'] = None
                                success.append("level")
                            else:
                                error = _('entered something invalid. Levels can\'t be higher than 40')
                        elif "disguise" in value and "disguise" not in success and pokemon.name.lower() == "ditto":
                            if value_split[1] and value_split[1].lower() in self.bot.pkmn_info.keys():
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['disguise'] = value_split[1].title()
                                success.append("disguise")
                            elif value_split[1] and value_split[1].lower() == "none":
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['disguise'] = None
                                success.append("disguise")
                            else:
                                error = _('entered something invalid. Levels can\'t be higher than 40')
                        elif "weather" in value and "weather" not in success:
                            if "rain" in value:
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['weather'] = "rainy"
                                success.append("weather")
                            elif "partly" in value:
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['weather'] = "partlycloudy"
                                success.append("weather")
                            elif "clear" in value or "sunny" in value:
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['weather'] = "clear"
                                success.append("weather")
                            elif "cloudy" in value or "overcast" in value:
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['weather'] = "cloudy"
                                success.append("weather")
                            elif "wind" in value:
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['weather'] = "windy"
                                success.append("weather")
                            elif "snow" in value:
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['weather'] = "snowy"
                                success.append("weather")
                            elif "fog" in value:
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['weather'] = "foggy"
                                success.append("weather")
                            elif value_split[1] and value_split[1].lower() == "none":
                                self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['weather'] = None
                                success.append("weather")
                            else:
                                error = _("entered something invalid. Choose from rainy, partly cloudy, clear, sunny, cloudy, overcast, windy, snowy, foggy")
                        else:
                            error = _("entered something invalid")
                    break
        if success:
            await self.edit_wild_messages(ctx, message)
        else:
            error = _("didn't change anything")
        if error:
            wild_embed.clear_fields()
            wild_embed.add_field(name=_('**Wild Edit Cancelled**'), value=f"Meowth! Your edit has been cancelled because you **{error}**! Retry when you're ready.", inline=False)
            if success:
                wild_embed.set_field_at(0, name="**Wild Edit Error**", value=f"Meowth! Your **{(', ').join(success)}** edits were successful, but others were skipped because you **{error}**! Retry when you're ready.", inline=False)
            confirmation = await channel.send(embed=wild_embed, delete_after=10)

    async def edit_wild_messages(self, ctx, message):
        wild_dict = self.bot.guild_dict[ctx.guild.id]['wildreport_dict'].get(message.id, {})
        dm_dict = wild_dict.get('dm_dict', {})
        gender = wild_dict.get('gender') if wild_dict.get('gender') else ''
        size = wild_dict.get('size') if wild_dict.get('size') else ''
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, f"{gender.lower()} {size.lower()} {wild_dict['pkmn_obj'].lower()}")
        iv_percent = wild_dict.get('wild_iv', {}).get('percent', None)
        level = wild_dict.get('level', None)
        old_embed = message.embeds[0]
        wild_gmaps_link = old_embed.url
        nearest_stop = wild_dict.get('location', None)
        poi_info = wild_dict.get('poi_info')
        author = ctx.guild.get_member(wild_dict.get('report_author', None))
        if author:
            ctx.author = author
        wild_embed = await self.make_wild_embed(ctx, wild_dict)
        content = message.content
        result = re.search('Wild (.*) reported by', content).group(1)
        content = content.replace(result, str(pokemon))
        if (iv_percent or iv_percent == 0) and "IV**" in content:
            content = re.sub(r" - \*\*[0-9]{1,3}IV\*\*", f" - **{iv_percent}IV**", content, flags=re.IGNORECASE)
        elif iv_percent or iv_percent == 0:
            content = content.splitlines()
            content[0] = f"{content[0]} - **{iv_percent}IV**"
            content = ('\n').join(content)
        try:
            await message.edit(content=content, embed=wild_embed)
        except:
            pass
        if isinstance(wild_embed.description, discord.embeds._EmptyEmbed):
            wild_embed.description = ""
        if "Jump to Message" not in wild_embed.description:
            wild_embed.description = wild_embed.description + f"\n**Report:** [Jump to Message]({message.jump_url})"
        new_description = str(wild_embed.description)
        index = 0
        for field in wild_embed.fields:
            if "reaction" in field.name.lower():
                wild_embed.remove_field(index)
            else:
                index += 1
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
                content = content.replace(result, str(pokemon))
                wild_embed.description = dm_message.embeds[0].description
                if (iv_percent or iv_percent == 0) and "IV**" in content:
                    content = re.sub(r" - \*\*[0-9]{1,3}IV\*\*", f" - **{iv_percent}IV**", content, flags=re.IGNORECASE)
                elif iv_percent or iv_percent == 0:
                    content = content.splitlines()
                    content[0] = f"{content[0]} - **{iv_percent}IV**"
                    content = ('\n').join(content)
                await dm_message.edit(content=content, embed=wild_embed)
            except:
                pass
        wild_embed.description = new_description
        ctx.wildreportmsg = message
        dm_dict = await self.send_dm_messages(ctx, str(pokemon), nearest_stop, iv_percent, level, content, copy.deepcopy(wild_embed), dm_dict)
        self.bot.guild_dict[ctx.guild.id]['wildreport_dict'][message.id]['dm_dict'] = dm_dict

    async def send_dm_messages(self, ctx, wild_pokemon, wild_details, wild_iv, wild_level, content, embed, dm_dict):
        if embed:
            if isinstance(embed.description, discord.embeds._EmptyEmbed):
                embed.description = ""
            if "Jump to Message" not in embed.description:
                embed.description = embed.description + f"\n**Report:** [Jump to Message]({ctx.wildreportmsg.jump_url})"
            index = 0
            for field in embed.fields:
                if "reaction" in field.name.lower():
                    embed.remove_field(index)
                else:
                    index += 1
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, wild_pokemon)
        content = content.splitlines()[0]
        wild_types = pokemon.types.copy()
        wild_types.append('None')
        for trainer in copy.deepcopy(self.bot.guild_dict[ctx.guild.id].get('trainers', {})):
            user_wants = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('wants', [])
            user_forms = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('forms', [])
            pokemon_setting = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].get('alerts', {}).get('settings', {}).get('categories', {}).get('pokemon', {}).get('wild', True)
            user_stops = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('stops', [])
            stop_setting = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].get('alerts', {}).get('settings', {}).get('categories', {}).get('pokestop', {}).get('wild', True)
            user_types = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('types', [])
            type_setting = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].get('alerts', {}).get('settings', {}).get('categories', {}).get('type', {}).get('wild', True)
            user_ivs = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('ivs', [])
            user_levels = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('levels', [])
            if not any([user_wants, user_forms, pokemon_setting, user_stops, stop_setting, user_types, type_setting, user_ivs, user_levels]):
                continue
            if not checks.dm_check(ctx, trainer, "wild") or trainer in dm_dict:
                continue
            send_wild = []
            if pokemon_setting and pokemon and pokemon.id in user_wants:
                send_wild.append(f"Pokemon: {pokemon.name.title()}")
            if pokemon_setting and pokemon and str(pokemon) in user_forms:
                send_wild.append(f"Pokemon Form: {str(pokemon)}")
            if stop_setting and str(wild_details).lower() in user_stops:
                send_wild.append(f"Pokestop: {wild_details.title()}")
            if type_setting and wild_types[0].lower() in user_types:
                type_emoji = utils.parse_emoji(ctx.guild, self.bot.config.type_id_dict[wild_types[0].lower()])
                send_wild.append(f"Type: {type_emoji}")
            if type_setting and wild_types[1].lower() in user_types:
                type_emoji = utils.parse_emoji(ctx.guild, self.bot.config.type_id_dict[wild_types[1].lower()])
                send_wild.append(f"Type: {type_emoji}")
            if wild_iv in user_ivs:
                send_wild.append(f"IV: {wild_iv}")
            if wild_level in user_levels:
                send_wild.append(f"Level: {wild_level}")
            if send_wild:
                embed.description = embed.description + f"\n**Subscription:** {(', ').join(send_wild)}"
                try:
                    user = ctx.guild.get_member(trainer)
                    wilddmmsg = await user.send(content=content, embed=embed)
                    dm_dict[user.id] = wilddmmsg.id
                except:
                    continue
                embed.description = embed.description.replace(f"\n**Subscription:** {(', ').join(send_wild)}", "")
        return dm_dict

    @commands.group(aliases=['w'], invoke_without_command=True, case_insensitive=True)
    @checks.allowwildreport()
    async def wild(self, ctx, pokemon=None, *, location=None):
        """Report a wild Pokemon spawn location.

        Usage: !wild <species> <location> [iv]
        Guided report available with just !wild

        Meowth will insert the details (really just everything after the species name) into a
        Google maps link and post the link to the same channel the report was made in."""
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        error = False
        wild_iv = None
        wild_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_grass.png?cache=1')
        wild_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        wild_dict = self.bot.guild_dict[ctx.guild.id].setdefault('wildreport_dict', {})
        while True:
            async with ctx.typing():
                if pokemon and location:
                    content = f"{pokemon} {location}"
                    return await self._wild(ctx, content)
                else:
                    wild_embed.add_field(name=_('**New Wild Report**'), value=_("Meowth! I'll help you report a wild!\n\nFirst, I'll need to know what **pokemon** you encountered. Reply with the name of a **pokemon**. Include any forms, size, gender if necessary. You can reply with **cancel** to stop anytime."), inline=False)
                    mon_wait = await channel.send(embed=wild_embed)
                    def check(reply):
                        if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                            return True
                        else:
                            return False
                    try:
                        mon_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        mon_msg = None
                    await utils.safe_delete(mon_wait)
                    if not mon_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(mon_msg)
                    if mon_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    else:
                        pokemon, __ = await pkmn_class.Pokemon.ask_pokemon(ctx, mon_msg.clean_content)
                        if not pokemon:
                            error = _("entered an invalid pokemon")
                            break
                    await utils.safe_delete(mon_msg)
                    pokemon.shiny = False
                    pokemon.shadow = False
                    wild_embed.set_field_at(0, name=wild_embed.fields[0].name, value=f"Great! Now, reply with the **gym, pokestop, or other location** that the wild {str(pokemon)} is closest to. You can reply with **cancel** to stop anytime.", inline=False)
                    wild_embed.set_thumbnail(url=pokemon.img_url)
                    location_wait = await channel.send(embed=wild_embed)
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
                    wild_embed.set_field_at(0, name=wild_embed.fields[0].name, value=f"Fantastic! Now, did you check the **IV** for the {str(pokemon)} near {location}? Reply with the **IV** or **N** to report without IV. You can reply with **cancel** to stop anytime.", inline=False)
                    iv_wait = await channel.send(embed=wild_embed)
                    try:
                        iv_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        iv_msg = None
                    await utils.safe_delete(iv_wait)
                    if not iv_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(iv_msg)
                    if iv_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif iv_msg:
                        iv_test = iv_msg.clean_content
                        iv_test = iv_test.lower().strip()
                        if "iv" in iv_test or utils.is_number(iv_test):
                            wild_iv = iv_test.replace("iv", "").replace("@", "").replace("#", "")
                            if utils.is_number(wild_iv) and float(wild_iv) >= 0 and float(wild_iv) <= 100:
                                wild_iv = int(round(float(wild_iv)))
                            else:
                                wild_iv = None
                    break
        if not error:
            content = f"{pokemon} {location} {wild_iv if wild_iv else ''}"
            await self._wild(ctx, content)
        else:
            wild_embed.clear_fields()
            wild_embed.add_field(name=_('**Wild Report Cancelled**'), value=_("Meowth! Your report has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=wild_embed, delete_after=10)
            if not message.embeds:
                await utils.safe_delete(message)

    async def _wild(self, ctx, content):
        message = ctx.message
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))).strftime(_('%I:%M %p (%H:%M)'))
        wild_split = content.split()
        wild_iv = None
        nearest_stop = ""
        omw_emoji = self.bot.custom_emoji.get('wild_omw', u'\U0001F3CE\U0000fe0f')
        expire_emoji = self.bot.custom_emoji.get('wild_despawn', u'\U0001F4A8')
        catch_emoji = ctx.bot.custom_emoji.get('wild_catch', u'\U000026be')
        info_emoji = ctx.bot.custom_emoji.get('wild_info', u'\U00002139\U0000fe0f')
        report_emoji = self.bot.custom_emoji.get('wild_report', u'\U0001F4E2')
        list_emoji = ctx.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f')
        react_list = [omw_emoji, catch_emoji, expire_emoji, info_emoji, report_emoji, list_emoji]
        converter = commands.clean_content()
        iv_test = await converter.convert(ctx, content.split()[-1])
        iv_test = iv_test.lower().strip()
        if "iv" in iv_test or utils.is_number(iv_test):
            wild_iv = iv_test.replace("iv", "").replace("@", "").replace("#", "")
            if utils.is_number(wild_iv) and float(wild_iv) >= 0 and float(wild_iv) <= 100:
                wild_iv = int(round(float(wild_iv)))
                content = content.replace(content.split()[-1], "").strip()
            else:
                wild_iv = None
        pokemon, match_list = await pkmn_class.Pokemon.ask_pokemon(ctx, content)
        if pokemon:
            pokemon.shiny = False
            pokemon.shadow = False
        else:
            return await ctx.invoke(self.bot.get_command('wild'))
        for word in match_list:
            content = re.sub(word, "", content)
        wild_details = content.strip()
        if not wild_details:
            return await ctx.invoke(self.bot.get_command('wild'))
        expiremsg = _('**This {pokemon} has despawned!**').format(pokemon=pokemon.name.title())
        wild_gmaps_link = utils.create_gmaps_query(self.bot, wild_details, message.channel, type="wild")
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        poi_info = ""
        wild_coordinates = ""
        if gym_matching_cog:
            poi_info, wild_details, poi_url = await gym_matching_cog.get_poi_info(ctx, wild_details.replace(f" - **{wild_iv}IV**", "").strip(), "wild")
            if poi_url:
                wild_gmaps_link = poi_url
                wild_coordinates = poi_url.split("query=")[1]
                nearest_stop = await gym_matching_cog.find_nearest_stop((wild_coordinates.split(",")[0],wild_coordinates.split(",")[1]), ctx.guild.id)
        if not wild_details:
            await utils.safe_delete(ctx.message)
            return
        if wild_iv or wild_iv == 0:
            iv_str = f" - **{wild_iv}IV**"
            iv_percent = copy.copy(wild_iv)
            wild_iv = {'percent':wild_iv, 'iv_atk':None, 'iv_def':None, 'iv_sta':None}
        else:
            iv_str = ""
            iv_percent = None
            wild_iv = {}
        if nearest_stop and nearest_stop != wild_details:
            stop_str = f" | Nearest Pokestop: {nearest_stop}{iv_str}"
        else:
            stop_str = iv_str
        details = {
            'pkmn_obj':str(pokemon),
            'location': f"{nearest_stop if nearest_stop else wild_details}",
            'expire':'45 min 0 sec',
            'gender':pokemon.gender,
            'wild_iv':wild_iv
        }
        despawn = 2700
        wild_embed = await self.make_wild_embed(ctx, details)
        ctx.wildreportmsg = await message.channel.send(f"Meowth! Wild {str(pokemon).title()} reported by {message.author.mention}! Details: {wild_details}{stop_str}\n\nUse {omw_emoji} if coming, {catch_emoji} if caught, {expire_emoji} if despawned, {info_emoji} to edit details, {report_emoji} to report new, or {list_emoji} to list all wilds!", embed=wild_embed)
        dm_dict = {}
        dm_dict = await self.send_dm_messages(ctx, str(pokemon), nearest_stop, iv_percent, None, ctx.wildreportmsg.content.replace(ctx.author.mention, f"{ctx.author.display_name} in {ctx.channel.mention}"), copy.deepcopy(wild_embed), dm_dict)
        for reaction in react_list:
            await asyncio.sleep(0.25)
            await utils.safe_reaction(ctx.wildreportmsg, reaction)
        self.bot.guild_dict[message.guild.id]['wildreport_dict'][ctx.wildreportmsg.id] = {
            'report_time':time.time(),
            'exp':time.time() + despawn,
            'expedit': {"content":ctx.wildreportmsg.content, "embedcontent":expiremsg},
            'report_message':message.id,
            'report_channel':message.channel.id,
            'report_author':message.author.id,
            'report_guild':message.guild.id,
            'dm_dict':dm_dict,
            'location':wild_details,
            'coordinates':wild_coordinates,
            'url':wild_gmaps_link,
            'pokemon':pokemon.name.lower(),
            'pkmn_obj':str(pokemon),
            'wild_iv':wild_iv,
            'level':None,
            'cp':None,
            'size':pokemon.size,
            'gender':pokemon.gender,
            'omw':[],
            'caught_by':[]
        }
        if not ctx.author.bot:
            wild_reports = self.bot.guild_dict[message.guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('reports', {}).setdefault('wild', 0) + 1
            self.bot.guild_dict[message.guild.id]['trainers'][message.author.id]['reports']['wild'] = wild_reports
        if "ditto" in str(pokemon).lower():
            ditto_wait = await message.channel.send(f"{ctx.author.mention}, what was the Ditto hiding as?", delete_after=30)
            def check(reply):
                if reply.author is not ctx.guild.me and reply.channel.id == ctx.channel.id and reply.author == ctx.author:
                    return True
                else:
                    return False
            try:
                ditto_msg = await self.bot.wait_for('message', timeout=60, check=check)
            except asyncio.TimeoutError:
                ditto_msg = None
            await utils.safe_bulk_delete(ctx.channel, [ditto_wait, ditto_msg])
            if ditto_msg:
                pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, ditto_msg.clean_content.lower())
                self.bot.guild_dict[message.guild.id]['wildreport_dict'][ctx.wildreportmsg.id]['disguise'] = str(pokemon)
                await self.edit_wild_messages(ctx, ctx.wildreportmsg)

    @wild.command(aliases=['expire'])
    @checks.allowwildreport()
    @commands.has_permissions(manage_channels=True)
    async def reset(self, ctx, *, report_message=None):
        """Resets all wild reports.

        Usage: !wild reset [message ID]
        Will either reset [message] or all if no message is supplied"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel

        # get settings
        wild_dict = copy.deepcopy(self.bot.guild_dict[guild.id].setdefault('wildreport_dict', {}))
        await utils.safe_delete(message)

        if not wild_dict:
            return
        if report_message and int(report_message) in wild_dict.keys():
            try:
                report_message = await channel.fetch_message(report_message)
                await self.expire_wild(report_message)
            except:
                self.bot.loop.create_task(utils.expire_dm_reports(self.bot, self.bot.guild_dict[guild.id]['wild_dict'][report_message].get('dm_dict', {})))
                del self.bot.guild_dict[guild.id]['wild_dict'][report_message]
            return
        rusure = await channel.send(_('**Meowth!** Are you sure you\'d like to remove all wild reports?'))
        try:
            timeout = False
            res, reactuser = await utils.ask(self.bot, rusure, author.id)
        except TypeError:
            timeout = True
        if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', u'\U0000274e'):
            await utils.safe_delete(rusure)
            confirmation = await channel.send(_('Manual reset cancelled.'), delete_after=10)
            return
        elif res.emoji == self.bot.custom_emoji.get('answer_yes', u'\U00002705'):
            await utils.safe_delete(rusure)
            async with ctx.typing():
                for report in wild_dict:
                    try:
                        report_message = await channel.fetch_message(report)
                        self.bot.loop.create_task(self.expire_wild(report_message))
                    except:
                        self.bot.loop.create_task(utils.expire_dm_reports(self.bot, self.bot.guild_dict[guild.id]['wild_dict'][report].get('dm_dict', {})))
                        del self.bot.guild_dict[guild.id]['wild_dict'][report]
                confirmation = await channel.send(_('Wilds reset.'), delete_after=10)
                return
        else:
            return

def setup(bot):
    bot.add_cog(Wild(bot))

def teardown(bot):
    bot.remove_cog(Wild)
