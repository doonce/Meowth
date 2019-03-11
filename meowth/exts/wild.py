import asyncio
import copy
import re
import time
import datetime
import dateparser
import textwrap
import logging

import discord
from discord.ext import commands

from meowth import utils, checks
from meowth.exts import pokemon as pkmn_class

logger = logging.getLogger("meowth")

class Wild(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.loop.create_task(self.wild_cleanup())

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        channel = self.bot.get_channel(payload.channel_id)
        try:
            message = await channel.get_message(payload.message_id)
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
            if str(payload.emoji) == self.bot.config['wild_omw']:
                wild_dict['omw'].append(user.mention)
                self.bot.guild_dict[guild.id]['wildreport_dict'][message.id] = wild_dict
            elif str(payload.emoji) == self.bot.config['wild_despawn']:
                for reaction in message.reactions:
                    if reaction.emoji == self.bot.config['wild_despawn'] and reaction.count >= 2:
                        if wild_dict['omw']:
                            despawn = _("has despawned")
                            await channel.send(f"{', '.join(wild_dict['omw'])}: {wild_dict['pokemon'].title()} {despawn}!")
                        await self.expire_wild(message)

    async def wild_cleanup(self, loop=True):
        while (not self.bot.is_closed()):
            await self.bot.wait_until_ready()
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
                                report_message = await report_channel.get_message(reportid)
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
            await asyncio.sleep(min(despawn_list))
            continue

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
            user_message = await channel.get_message(wild_dict[message.id]['reportmessage'])
            await utils.safe_delete(user_message)
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, KeyError):
            pass
        await utils.expire_dm_reports(self.bot, wild_dict.get(message.id, {}).get('dm_dict', {}))
        try:
            del self.bot.guild_dict[guild.id]['wildreport_dict'][message.id]
        except KeyError:
            pass

    @commands.group(aliases=['w'], invoke_without_command=True, case_insensitive=True)
    @checks.allowwildreport()
    async def wild(self, ctx, pokemon, *, location):
        """Report a wild Pokemon spawn location.

        Usage: !wild <species> <location>
        Meowth will insert the details (really just everything after the species name) into a
        Google maps link and post the link to the same channel the report was made in."""
        content = f"{pokemon} {location}"
        await self._wild(ctx, content)

    async def _wild(self, ctx, content):
        message = ctx.message
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])).strftime(_('%I:%M %p (%H:%M)'))
        wild_split = content.split()
        pokemon, match_list = await pkmn_class.Pokemon.ask_pokemon(ctx, content)
        if pokemon:
            entered_wild = pokemon.name.lower()
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
        wild_number = pokemon.id
        wild_img_url = pokemon.img_url
        wild_types = copy.deepcopy(pokemon.types)
        wild_types.append('None')
        expiremsg = _('**This {pokemon} has despawned!**').format(pokemon=entered_wild.title())
        wild_gmaps_link = utils.create_gmaps_query(self.bot, wild_details, message.channel, type="wild")
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        stop_info = ""
        if gym_matching_cog:
            stop_info, wild_details, stop_url = await gym_matching_cog.get_stop_info(ctx, wild_details)
            if stop_url:
                wild_gmaps_link = stop_url
        if not wild_details:
            await utils.safe_delete(ctx.message)
            return
        wild_embed = discord.Embed(title=_('Meowth! Click here for my directions to the wild {pokemon}!').format(pokemon=entered_wild.title()), description=_("Ask {author} if my directions aren't perfect!").format(author=message.author.name), url=wild_gmaps_link, colour=message.guild.me.colour)
        wild_embed.add_field(name=_('**Details:**'), value=_('{pokemon} ({pokemonnumber}) {type}').format(pokemon=entered_wild.capitalize(), pokemonnumber=str(wild_number), type=''.join(utils.get_type(self.bot, message.guild, pokemon.id, pokemon.form, pokemon.alolan))), inline=False)
        wild_embed.set_thumbnail(url=wild_img_url)
        wild_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=message.author.display_name, timestamp=timestamp), icon_url=message.author.avatar_url_as(format=None, static_format='jpg', size=32))
        despawn = 3600
        wild_embed.add_field(name='**Reactions:**', value=_("{emoji}: I'm on my way!").format(emoji=self.bot.config['wild_omw']))
        wild_embed.add_field(name='\u200b', value=_("{emoji}: The Pokemon despawned!").format(emoji=self.bot.config['wild_despawn']))
        wildreportmsg = await message.channel.send(content=_('Meowth! Wild {pokemon} reported by {member}! Details: {location_details}').format(pokemon=str(pokemon).title(), member=message.author.mention, location_details=wild_details), embed=wild_embed)
        dm_dict = {}
        for trainer in self.bot.guild_dict[message.guild.id].get('trainers', {}):
            if not checks.dm_check(ctx, trainer):
                continue
            user_wants = self.bot.guild_dict[message.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('wants', [])
            user_stops = self.bot.guild_dict[message.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('stops', [])
            user_types = self.bot.guild_dict[message.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('types', [])
            if wild_number in user_wants or wild_types[0].lower() in user_types or wild_types[1].lower() in user_types or wild_details.lower() in user_stops:
                try:
                    user = ctx.guild.get_member(trainer)
                    wild_embed.remove_field(1)
                    wild_embed.remove_field(1)
                    wilddmmsg = await user.send(content=_('Meowth! Wild {pokemon} reported by {member} in {channel}! Details: {location_details}').format(pokemon=str(pokemon).title(), member=message.author.display_name, channel=message.channel.mention, location_details=wild_details), embed=wild_embed)
                    dm_dict[user.id] = wilddmmsg.id
                except:
                    continue
        await asyncio.sleep(0.25)
        await wildreportmsg.add_reaction(self.bot.config['wild_omw'])
        await asyncio.sleep(0.25)
        await wildreportmsg.add_reaction(self.bot.config['wild_despawn'])
        await asyncio.sleep(0.25)
        self.bot.guild_dict[message.guild.id]['wildreport_dict'][wildreportmsg.id] = {
            'exp':time.time() + despawn,
            'expedit': {"content":wildreportmsg.content, "embedcontent":expiremsg},
            'reportmessage':message.id,
            'reportchannel':message.channel.id,
            'reportauthor':message.author.id,
            'dm_dict':dm_dict,
            'location':wild_details,
            'url':wild_gmaps_link,
            'pokemon':entered_wild,
            'pkmn_obj':str(pokemon),
            'omw':[]
        }
        wild_reports = self.bot.guild_dict[message.guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('wild_reports', 0) + 1
        self.bot.guild_dict[message.guild.id]['trainers'][message.author.id]['wild_reports'] = wild_reports

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
            report_message = await channel.get_message(report_message)
            await self.expire_wild(report_message)
            return
        rusure = await channel.send(_('**Meowth!** Are you sure you\'d like to remove all wild reports?'))
        try:
            timeout = False
            res, reactuser = await utils.ask(self.bot, rusure, author.id)
        except TypeError:
            timeout = True
        if timeout or res.emoji == self.bot.config['answer_no']:
            await utils.safe_delete(rusure)
            confirmation = await channel.send(_('Manual reset cancelled.'), delete_after=10)
            return
        elif res.emoji == self.bot.config['answer_yes']:
            await utils.safe_delete(rusure)
            for report in wild_dict:
                report_message = await channel.get_message(report)
                await self.expire_wild(report_message)
            confirmation = await channel.send(_('Wilds reset.'), delete_after=10)
            return
        else:
            return

def setup(bot):
    bot.add_cog(Wild(bot))
