import asyncio
import copy
import re
import time
import datetime
import dateparser
import textwrap
import logging

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
        try:
            wildreport_dict = self.bot.guild_dict[guild.id]['wildreport_dict']
        except KeyError:
            wildreport_dict = []
        if message.id in wildreport_dict and user.id != self.bot.user.id:
            wild_dict = self.bot.guild_dict[guild.id]['wildreport_dict'][message.id]
            if str(payload.emoji) == self.bot.config.get('wild_omw', '\ud83c\udfce'):
                wild_dict['omw'].append(user.mention)
                self.bot.guild_dict[guild.id]['wildreport_dict'][message.id] = wild_dict
            elif str(payload.emoji) == self.bot.config.get('wild_despawn', '\ud83d\udca8'):
                for reaction in message.reactions:
                    if reaction.emoji == self.bot.config.get('wild_despawn', '\ud83d\udca8') and reaction.count >= 2:
                        if wild_dict['omw']:
                            despawn = _("has despawned")
                            await channel.send(f"{', '.join(wild_dict['omw'])}: {wild_dict['pokemon'].title()} {despawn}!")
                        await self.expire_wild(message)

    @tasks.loop(seconds=0)
    async def wild_cleanup(self, loop=True):
        while True:
            logger.info('------ BEGIN ------')
            guilddict_temp = copy.deepcopy(self.bot.guild_dict)
            despawn_list = []
            count = 0
            for guildid in guilddict_temp.keys():
                wild_dict = guilddict_temp[guildid].setdefault('wildreport_dict', {})
                for reportid in wild_dict.keys():
                    if wild_dict[reportid].get('exp', 0) <= time.time():
                        report_channel = self.bot.get_channel(wild_dict[reportid].get('reportchannel'))
                        if report_channel:
                            try:
                                report_message = await report_channel.fetch_message(reportid)
                                self.bot.loop.create_task(self.expire_wild(report_message))
                                count += 1
                                continue
                            except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                                pass
                        try:
                            del self.bot.guild_dict[guildid]['wildreport_dict'][reportid]
                        except KeyError:
                            continue
                    to_despawn = wild_dict[reportid].get('exp', 0) - time.time()
                    despawn_list.append(to_despawn)
            # save server_dict changes after cleanup
            logger.info('SAVING CHANGES')
            try:
                await self.bot.save()
            except Exception as err:
                logger.info('SAVING FAILED' + err)
                pass
            if not despawn_list:
                despawn_list = [600]
            logger.info(f"------ END - {count} Wilds Cleaned - Waiting {min(despawn_list)} seconds. ------")
            if not loop:
                return
            await asyncio.sleep(min(despawn_list))
            continue

    @wild_cleanup.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    async def expire_wild(self, message):
        guild = message.channel.guild
        channel = message.channel
        wild_dict = copy.deepcopy(self.bot.guild_dict[guild.id]['wildreport_dict'])
        try:
            await message.edit(embed=discord.Embed(description=wild_dict[message.id]['expedit']['embedcontent'], colour=message.embeds[0].colour.value))
            await message.clear_reactions()
        except (discord.errors.NotFound, KeyError):
            pass
        try:
            user_message = await channel.fetch_message(wild_dict[message.id]['reportmessage'])
            await utils.safe_delete(user_message)
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, KeyError):
            pass
        await utils.expire_dm_reports(self.bot, wild_dict.get(message.id, {}).get('dm_dict', {}))
        try:
            del self.bot.guild_dict[guild.id]['wildreport_dict'][message.id]
        except KeyError:
            pass

    async def send_dm_messages(self, ctx, wild_number, wild_details, wild_type_1, wild_type_2, wild_iv, content, embed, dm_dict):
        if embed:
            if isinstance(embed.description, discord.embeds._EmptyEmbed):
                embed.description = ""
            embed.description = embed.description + f"\n**Report:** [Jump to Message]({ctx.wildreportmsg.jump_url})"
            embed.remove_field(len(embed.fields)-1)
            embed.remove_field(len(embed.fields)-1)
        for trainer in self.bot.guild_dict[ctx.guild.id].get('trainers', {}):
            if not checks.dm_check(ctx, trainer):
                continue
            if trainer in dm_dict:
                continue
            user_wants = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('wants', [])
            user_stops = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('stops', [])
            user_types = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('types', [])
            user_ivs = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('ivs', [])
            if wild_number in user_wants or wild_type_1.lower() in user_types or wild_type_2.lower() in user_types or wild_details.lower() in user_stops or wild_iv in user_ivs:
                try:
                    user = ctx.guild.get_member(trainer)
                    wilddmmsg = await user.send(content=content, embed=embed)
                    dm_dict[user.id] = wilddmmsg.id
                except:
                    continue
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
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset']))
        error = False
        wild_iv = None
        wild_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/ic_grass.png?cache=1')
        wild_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        while True:
            async with ctx.typing():
                if pokemon and location:
                    content = f"{pokemon} {location}"
                    await self._wild(ctx, content)
                    return
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
                        pokemon, __ = await pkmn_class.Pokemon.ask_pokemon(ctx, mon_msg.clean_content, allow_digits=False)
                        if not pokemon:
                            error = _("entered an invalid pokemon")
                            break
                    await utils.safe_delete(mon_msg)
                    pokemon.shiny = False
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
                    wild_embed.set_field_at(0, name=wild_embed.fields[0].name, value=f"Fantastic! Now, did you check the **IV** for the {str(pokemon)}? Reply with the **IV** or **N** to report without IV. You can reply with **cancel** to stop anytime.", inline=False)
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
            wild_embed.add_field(name=_('**Raid Report Cancelled**'), value=_("Meowth! Your report has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=wild_embed, delete_after=10)
            await utils.safe_delete(message)

    async def _wild(self, ctx, content):
        message = ctx.message
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])).strftime(_('%I:%M %p (%H:%M)'))
        wild_split = content.split()
        pokemon, match_list = await pkmn_class.Pokemon.ask_pokemon(ctx, content)
        wild_iv = None
        nearest_stop = ""
        if pokemon:
            pokemon.shiny = False
        else:
            await message.channel.send(_('Meowth! Give more details when reporting! Usage: **!wild <pokemon name> <location>**'), delete_after=10)
            return

        for word in match_list:
            content = re.sub(word, "", content)
        wild_details = content.strip()
        if not wild_details:
            await message.channel.send(_('Meowth! Give more details when reporting! Usage: **!wild <pokemon name> <location>**'), delete_after=10)
            return
        converter = commands.clean_content()
        iv_test = await converter.convert(ctx, wild_details.split()[-1])
        iv_test = iv_test.lower().strip()
        if "iv" in iv_test or utils.is_number(iv_test):
            wild_iv = iv_test.replace("iv", "").replace("@", "").replace("#", "")
            if utils.is_number(wild_iv) and float(wild_iv) >= 0 and float(wild_iv) <= 100:
                wild_iv = int(round(float(wild_iv)))
                wild_details = wild_details.replace(wild_details.split()[-1], "").strip()
            else:
                wild_iv = None
        wild_types = copy.deepcopy(pokemon.types)
        wild_types.append('None')
        expiremsg = _('**This {pokemon} has despawned!**').format(pokemon=pokemon.name.title())
        wild_gmaps_link = utils.create_gmaps_query(self.bot, wild_details, message.channel, type="wild")
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        poi_info = ""
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
        else:
            iv_str = ""
        if nearest_stop and nearest_stop != wild_details:
            stop_str = f" | Nearest Pokestop: {nearest_stop}"
        else:
            stop_str = ""
        shiny_str = ""
        if pokemon.id in self.bot.shiny_dict:
            if pokemon.alolan and "alolan" in self.bot.shiny_dict.get(pokemon.id, {}) and "wild" in self.bot.shiny_dict.get(pokemon.id, {}).get("alolan", []):
                shiny_str = self.bot.config.get('shiny_chance', '\u2728') + " "
            elif str(pokemon.form).lower() in self.bot.shiny_dict.get(pokemon.id, {}) and "wild" in self.bot.shiny_dict.get(pokemon.id, {}).get(str(pokemon.form).lower(), []):
                shiny_str = self.bot.config.get('shiny_chance', '\u2728') + " "
        wild_embed = discord.Embed(title=_('Meowth! Click here for my directions to the wild {pokemon}!').format(pokemon=pokemon.name.title()), description=_("Ask {author} if my directions aren't perfect!").format(author=message.author.name), url=wild_gmaps_link, colour=message.guild.me.colour)
        if nearest_stop:
            wild_embed.description = poi_info
        wild_embed.add_field(name=_('**Details:**'), value=f"{shiny_str}{pokemon.name.title()} ({pokemon.id}) {pokemon.emoji}", inline=False)
        wild_embed.set_thumbnail(url=pokemon.img_url)
        wild_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=message.author.display_name, timestamp=timestamp), icon_url=message.author.avatar_url_as(format=None, static_format='jpg', size=32))
        despawn = 3600
        wild_embed.add_field(name='**Reactions:**', value=_("{emoji}: I'm on my way!").format(emoji=self.bot.config.get('wild_omw', '\ud83c\udfce')))
        wild_embed.add_field(name='\u200b', value=_("{emoji}: The Pokemon despawned!").format(emoji=self.bot.config.get('wild_despawn', '\ud83d\udca8')))
        wild_embed.set_author(name=f"Wild {pokemon.name.title()} Report", icon_url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/ic_grass.png?cache=1")
        ctx.wildreportmsg = await message.channel.send(content=_('Meowth! Wild {pokemon} reported by {member}! Details: {location_details}{iv_str}{stop_str}').format(pokemon=str(pokemon).title(), member=message.author.mention, location_details=wild_details, iv_str=iv_str, stop_str=stop_str), embed=wild_embed)
        dm_dict = {}
        dm_dict = await self.send_dm_messages(ctx, pokemon.id, nearest_stop, wild_types[0], wild_types[1], wild_iv, ctx.wildreportmsg.content.replace(ctx.author.mention, f"{ctx.author.display_name} in {ctx.channel.mention}"), copy.deepcopy(wild_embed), dm_dict)
        await asyncio.sleep(0.25)
        await utils.safe_reaction(ctx.wildreportmsg, self.bot.config.get('wild_omw', '\ud83c\udfce'))
        await asyncio.sleep(0.25)
        await utils.safe_reaction(ctx.wildreportmsg, self.bot.config.get('wild_despawn', '\ud83d\udca8'))
        await asyncio.sleep(0.25)
        self.bot.guild_dict[message.guild.id]['wildreport_dict'][ctx.wildreportmsg.id] = {
            'exp':time.time() + despawn,
            'expedit': {"content":ctx.wildreportmsg.content, "embedcontent":expiremsg},
            'reportmessage':message.id,
            'reportchannel':message.channel.id,
            'reportauthor':message.author.id,
            'dm_dict':dm_dict,
            'location':wild_details,
            'url':wild_gmaps_link,
            'pokemon':pokemon.name.lower(),
            'pkmn_obj':str(pokemon),
            'wild_iv':wild_iv,
            'omw':[]
        }
        wild_reports = self.bot.guild_dict[message.guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('wild_reports', 0) + 1
        self.bot.guild_dict[message.guild.id]['trainers'][message.author.id]['wild_reports'] = wild_reports
        if "ditto" in str(pokemon).lower():
            await message.channel.send(f"{ctx.author.mention}, what was the Ditto hiding as?", delete_after=30)

    @wild.command(aliases=['expire'])
    @checks.allowwildreport()
    @commands.has_permissions(manage_channels=True)
    async def reset(self, ctx, *, report_message=None):
        """Resets all wild reports."""
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
            report_message = await channel.fetch_message(report_message)
            await self.expire_wild(report_message)
            return
        rusure = await channel.send(_('**Meowth!** Are you sure you\'d like to remove all wild reports?'))
        try:
            timeout = False
            res, reactuser = await utils.ask(self.bot, rusure, author.id)
        except TypeError:
            timeout = True
        if timeout or res.emoji == self.bot.config.get('answer_no', '\u274e'):
            await utils.safe_delete(rusure)
            confirmation = await channel.send(_('Manual reset cancelled.'), delete_after=10)
            return
        elif res.emoji == self.bot.config.get('answer_yes', '\u2705'):
            await utils.safe_delete(rusure)
            for report in wild_dict:
                report_message = await channel.fetch_message(report)
                self.bot.loop.create_task(self.expire_wild(report_message))
            confirmation = await channel.send(_('Wilds reset.'), delete_after=10)
            return
        else:
            return

def setup(bot):
    bot.add_cog(Wild(bot))
