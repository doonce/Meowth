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

class Invasion(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.invasion_cleanup.start()

    def cog_unload(self):
        self.invasion_cleanup.cancel()

    @tasks.loop(seconds=10)
    async def invasion_cleanup(self, loop=True):
        logger.info('------ BEGIN ------')
        expire_list = []
        count = 0
        for guild in list(self.bot.guilds):
            invasion_dict = self.bot.guild_dict[guild.id].setdefault('invasion_dict', {})
            for reportid in list(invasion_dict.keys()):
                if invasion_dict[reportid].get('exp', 0) <= time.time():
                    report_channel = self.bot.get_channel(invasion_dict[reportid].get('report_channel'))
                    if report_channel:
                        try:
                            report_message = await report_channel.fetch_message(reportid)
                            self.bot.loop.create_task(self.expire_invasion(report_message))
                            count += 1
                            continue
                        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                            pass
                    try:
                        self.bot.loop.create_task(utils.expire_dm_reports(self.bot, invasion_dict.get(reportid, {}).get('dm_dict', {})))
                        del self.bot.guild_dict[guild.id]['wildreport_dict'][reportid]
                        count += 1
                        continue
                    except KeyError:
                        continue
                to_expire = invasion_dict[reportid].get('exp', 0) - time.time()
                if to_expire > 10:
                    expire_list.append(to_expire)
        # save server_dict changes after cleanup
        logger.info('SAVING CHANGES')
        try:
            await self.bot.save
        except Exception as err:
            logger.info('SAVING FAILED' + str(err))
        if not expire_list:
            expire_list = [600]
        logger.info(f"------ END - {count} Invasions Cleaned - Waiting {min(expire_list)} seconds. ------")
        if not loop:
            return
        self.invasion_cleanup.change_interval(seconds=min(expire_list))

    @invasion_cleanup.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

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
        if user == self.bot.user:
            return
        guild = message.guild
        can_manage = channel.permissions_for(user).manage_messages
        try:
            invasion_dict = self.bot.guild_dict[guild.id]['invasion_dict']
        except KeyError:
            invasion_dict = {}
        if message.id in invasion_dict:
            invasion_dict =  self.bot.guild_dict[guild.id]['invasion_dict'][message.id]
            if str(payload.emoji) == self.bot.custom_emoji.get('invasion_complete', '\U0001f1f7'):
                if user.id not in invasion_dict.get('completed_by', []):
                    if user.id != invasion_dict['report_author']:
                        invasion_dict.get('completed_by', []).append(user.id)
            elif str(payload.emoji) == self.bot.custom_emoji.get('invasion_expired', '\U0001F4A8'):
                for reaction in message.reactions:
                    if reaction.emoji == self.bot.custom_emoji.get('invasion_expired', '\U0001F4A8') and (reaction.count >= 3 or can_manage):
                        await self.expire_invasion(message)
            elif str(payload.emoji) == self.bot.custom_emoji.get('wild_info', '\u2139'):
                ctx = await self.bot.get_context(message)
                if not ctx.prefix:
                    prefix = self.bot._get_prefix(self.bot, message)
                    ctx.prefix = prefix[-1]
                await message.remove_reaction(payload.emoji, user)
                ctx.author = user
                if not invasion_dict.get('pkmn_obj', None):
                    await self.add_invasion_info(ctx, message, user)

    async def expire_invasion(self, message):
        guild = message.channel.guild
        channel = message.channel
        invasion_dict = copy.deepcopy(self.bot.guild_dict[guild.id]['invasion_dict'])
        await utils.safe_delete(message)
        try:
            user_message = await channel.fetch_message(invasion_dict[message.id]['report_message'])
            await utils.safe_delete(user_message)
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, KeyError):
            pass
        await utils.expire_dm_reports(self.bot, invasion_dict[message.id].get('dm_dict', {}))
        invasion_bonus = invasion_dict.get(message.id, {}).get('completed_by', [])
        if len(invasion_bonus) >= 3 and not message.author.bot:
            invasion_reports = self.bot.guild_dict[message.guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('invasion_reports', 0) + 1
            self.bot.guild_dict[message.guild.id]['trainers'][message.author.id]['invasion_reports'] = invasion_reports
        try:
            del self.bot.guild_dict[guild.id]['invasion_dict'][message.id]
        except KeyError:
            pass

    async def add_invasion_info(self, ctx, message, user):
        invasion_dict = self.bot.guild_dict[ctx.guild.id]['invasion_dict'].get(message.id, {})
        message = ctx.message
        channel = message.channel
        guild = message.guild
        author = guild.get_member(invasion_dict.get('report_author', None))
        location = invasion_dict.get('location', '')
        info_emoji = ctx.bot.custom_emoji.get('wild_info', '\u2139')
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, invasion_dict.get('pkmn_obj', None))
        if not author:
            return
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[channel.guild.id]['configure_dict']['settings']['offset']))
        error = False
        invasion_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/teamrocket.png?cache=1')
        invasion_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        while True:
            async with ctx.typing():
                invasion_embed.add_field(name=_('**Edit Invasion Info**'), value=f"Meowth! I'll help you add the reward to the invasion! Reply with the **pokemon** Team Rocket is rewarding at the **{location}** invasion. You can reply with **cancel** to stop anytime.", inline=False)
                value_wait = await channel.send(embed=invasion_embed)
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
                    pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, value_msg.clean_content.lower())
                    if not pokemon:
                        error = _("didn't enter a pokemon")
                    else:
                        pokemon.shiny = False
                        pokemon.size = None
                        pokemon.form = "shadow" if "shadow" in self.bot.form_dict[pokemon.id] else None
                        self.bot.guild_dict[ctx.guild.id]['invasion_dict'][message.id]['reward'] = pokemon.name.lower()
                        self.bot.guild_dict[ctx.guild.id]['invasion_dict'][message.id]['pkmn_obj'] = str(pokemon)
                        if not user.bot:
                            if author.bot:
                                invasion_reports = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(user.id, {}).setdefault('invasion_reports', 0) + 1
                            else:
                                invasion_reports = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(user.id, {}).setdefault('invasion_reports', 0) + 0.5
                            self.bot.guild_dict[ctx.guild.id]['trainers'][user.id]['invasion_reports'] = invasion_reports
                    break
        if error:
            invasion_embed.clear_fields()
            invasion_embed.add_field(name=_('**Invasion Edit Cancelled**'), value=f"Meowth! Your edit has been cancelled because you **{error}**! Retry when you're ready.", inline=False)
            confirmation = await channel.send(embed=invasion_embed, delete_after=10)
        else:
            await message.remove_reaction(info_emoji, self.bot.user)
            await self.edit_invasion_messages(ctx, message)

    async def edit_invasion_messages(self, ctx, message):
        invasion_dict = self.bot.guild_dict[ctx.guild.id]['invasion_dict'].get(message.id, {})
        reward = invasion_dict.get('pkmn_obj', {})
        dm_dict = invasion_dict.get('dm_dict', {})
        old_embed = message.embeds[0]
        invasion_gmaps_link = old_embed.url
        nearest_stop = invasion_dict.get('location', None)
        complete_emoji = self.bot.custom_emoji.get('invasion_complete', '\U0001f1f7')
        expire_emoji = self.bot.custom_emoji.get('invasion_expired', '\ud83d\udca8')
        info_emoji = ctx.bot.custom_emoji.get('wild_info', '\u2139')
        author = ctx.guild.get_member(invasion_dict.get('report_author', None))
        if author:
            ctx.author = author
        shiny_str = ""
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, reward, allow_digits=False)
        if not pokemon:
            return
        pokemon.shiny = False
        pokemon.form = "shadow" if "shadow" in self.bot.form_dict[pokemon.id] else None
        if pokemon.id in self.bot.shiny_dict:
            if pokemon.alolan and "alolan" in self.bot.shiny_dict.get(pokemon.id, {}) and "research" in self.bot.shiny_dict.get(pokemon.id, {}).get("alolan", []):
                shiny_str = self.bot.custom_emoji.get('shiny_chance', '\u2728') + " "
            elif str(pokemon.form).lower() in self.bot.shiny_dict.get(pokemon.id, {}) and "research" in self.bot.shiny_dict.get(pokemon.id, {}).get(str(pokemon.form).lower(), []):
                shiny_str = self.bot.custom_emoji.get('shiny_chance', '\u2728') + " "
        reward = f"{shiny_str}{string.capwords(pokemon.name, ' ')} {pokemon.emoji}"
        index = 0
        for field in old_embed.fields:
            if "reward" in field.name.lower():
                old_embed.set_field_at(index, name=field.name, value=reward)
            else:
                index += 1
        reward = reward.replace(pokemon.emoji, "").replace(shiny_str, "").strip()
        invasion_embed = old_embed
        invasion_embed.set_thumbnail(url=pokemon.img_url)
        content = message.content.replace(f" or {info_emoji} to add the reward", "")
        try:
            await message.edit(content=content, embed=invasion_embed)
        except:
            pass
        if isinstance(invasion_embed.description, discord.embeds._EmptyEmbed):
            invasion_embed.description = ""
        if "Jump to Message" not in invasion_embed.description:
            invasion_embed.description = invasion_embed.description + f"\n**Report:** [Jump to Message]({message.jump_url})"
        for dm_user, dm_message in dm_dict.items():
            try:
                dm_user = self.bot.get_user(dm_user)
                dm_channel = dm_user.dm_channel
                if not dm_channel:
                    dm_channel = await dm_user.create_dm()
                if not dm_user or not dm_channel:
                    continue
                dm_message = await dm_channel.fetch_message(dm_message)
                content = f"{str(pokemon)} {dm_message.content}"
                await dm_message.edit(content=content, embed=invasion_embed)
            except:
                pass
        ctx.invreportmsg = message
        dm_dict = await self.send_dm_messages(ctx, str(pokemon), nearest_stop, copy.deepcopy(invasion_embed), dm_dict)
        self.bot.guild_dict[ctx.guild.id]['invasion_dict'][message.id]['dm_dict'] = dm_dict

    async def send_dm_messages(self, ctx, inv_pokemon, location, embed, dm_dict):
        if embed:
            if isinstance(embed.description, discord.embeds._EmptyEmbed):
                embed.description = ""
            if "Jump to Message" not in embed.description:
                embed.description = embed.description + f"\n**Report:** [Jump to Message]({ctx.invreportmsg.jump_url})"
            index = 0
            for field in embed.fields:
                if "reaction" in field.name.lower():
                    embed.remove_field(index)
                else:
                    index += 1
        pokemon = None
        if inv_pokemon != "Unknown Pokemon":
            pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, inv_pokemon)
        if pokemon:
            pkmn_types = pokemon.types.copy()
        else:
            pkmn_types = ['None']
        pkmn_types.append('None')
        for trainer in self.bot.guild_dict[ctx.guild.id].get('trainers', {}):
            user_categories = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('settings', {}).setdefault('categories', ["wild", "research", "invasion", "lure", "nest", "raid"])
            user_wants = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('wants', [])
            user_stops = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('stops', [])
            user_types = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('types', [])
            user_forms = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('forms', [])
            if not checks.dm_check(ctx, trainer):
                continue
            if trainer in dm_dict:
                continue
            if "invasion" not in user_categories:
                continue
            if (pokemon and pokemon.id in user_wants) or str(pokemon) in user_forms or str(location).lower() in user_stops or pkmn_types[0].lower() in user_types or pkmn_types[1].lower() in user_types:
                try:
                    user = ctx.guild.get_member(trainer)
                    if pokemon:
                        invdmmsg = await user.send(_("{pkmn} Invasion reported by {author} in {channel}!").format(pkmn=string.capwords(pokemon.name, ' '), author=ctx.author.display_name, channel=ctx.channel.mention), embed=embed)
                    else:
                        invdmmsg = await user.send(_("Invasion reported by {author} in {channel}!").format(author=ctx.author.display_name, channel=ctx.channel.mention), embed=embed)
                    dm_dict[user.id] = invdmmsg.id
                except Exception as e:
                    continue
        return dm_dict

    @commands.group(aliases=['inv'], invoke_without_command=True, case_insensitive=True)
    @checks.allowinvasionreport()
    async def invasion(self, ctx, *, details = None):
        """Report Invasion
        Guided report method with just !invasion. If you supply arguments in one
        line, avoid commas in anything but your separations between pokestop,
        and reward. Order matters if you supply arguments.

        Usage: !invasion [pokestop name [optional URL], reward]"""
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset']))
        exp_timestamp = (ctx.message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['offset'], minutes=30, seconds=0)).strftime('%I:%M %p')
        error = False
        loc_url = utils.create_gmaps_query(self.bot, "", message.channel, type="invasion")
        invasion_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/teamrocket.png?cache=1')
        invasion_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        pokemon = False
        invasion_dict = self.bot.guild_dict[ctx.guild.id].setdefault('invasion_dict', {})
        while True:
            async with ctx.typing():
                if details:
                    invasion_split = details.rsplit(",", 2)
                    invasion_split.append("None")
                    location, reward = invasion_split
                    gym_matching_cog = self.bot.cogs.get('GymMatching')
                    stop_info = ""
                    if gym_matching_cog:
                        stop_info, location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "invasion")
                        if stop_url:
                            loc_url = stop_url
                            invasion_embed.description = stop_info
                    if not location:
                        return
                    break
                else:
                    invasion_embed.add_field(name=_('**New Invasion Report**'), value=_("Meowth! I'll help you report a Team Rocket invasion!\n\nFirst, I'll need to know what **pokestop** Team Rocket has invaded. Reply with the name of the **pokestop**. You can reply with **cancel** to stop anytime."), inline=False)
                    pokestopwait = await channel.send(embed=invasion_embed)
                    def check(reply):
                        if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == message.author:
                            return True
                        else:
                            return False
                    try:
                        pokestopmsg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        pokestopmsg = None
                    await utils.safe_delete(pokestopwait)
                    if not pokestopmsg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(pokestopmsg)
                    if pokestopmsg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif pokestopmsg:
                        location = pokestopmsg.clean_content
                        gym_matching_cog = self.bot.cogs.get('GymMatching')
                        stop_info = ""
                        if gym_matching_cog:
                            stop_info, location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "invasion")
                            if stop_url:
                                loc_url = stop_url
                        if not location:
                            return
                    invasion_embed.set_field_at(0, name=invasion_embed.fields[0].name, value=_("Fantastic! Now, reply with the **reward** you earned for the invasion at the **{location}** pokestop. If you don't know the reward, reply with **N**. It is usually Team Rocket's first pokemon. You can reply with **cancel** to stop anytime").format(location=location), inline=False)
                    rewardwait = await channel.send(embed=invasion_embed)
                    try:
                        rewardmsg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        rewardmsg = None
                    await utils.safe_delete(rewardwait)
                    if not rewardmsg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(rewardmsg)
                    if rewardmsg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif rewardmsg.clean_content.lower() == "n":
                        reward = ''
                    elif rewardmsg:
                        reward = rewardmsg.clean_content
                    break
        if not error:
            await self.send_invasion(ctx, location, reward)
        else:
            invasion_embed.clear_fields()
            invasion_embed.add_field(name=_('**Invasion Report Cancelled**'), value=_("Meowth! Your report has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=invasion_embed, delete_after=10)
            await utils.safe_delete(message)

    async def send_invasion(self, ctx, location, reward='', timer=None):
        dm_dict = {}
        expire_time = "30"
        if timer:
            expire_time = timer
        invasion_dict = self.bot.guild_dict[ctx.guild.id].setdefault('invasion_dict', {})
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.message.channel.guild.id]['configure_dict']['settings']['offset']))
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['offset'])
        end = now + datetime.timedelta(minutes=int(expire_time))
        complete_emoji = self.bot.custom_emoji.get('invasion_complete', '\U0001f1f7')
        expire_emoji = self.bot.custom_emoji.get('invasion_expired', '\ud83d\udca8')
        info_emoji = ctx.bot.custom_emoji.get('wild_info', '\u2139')
        invasion_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/teamrocket.png?cache=1')
        shiny_str = ""
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, reward, allow_digits=False)
        if pokemon:
            pokemon.shiny = False
            pokemon.form = "shadow" if "shadow" in self.bot.form_dict[pokemon.id] else None
            if pokemon.id in self.bot.shiny_dict:
                if pokemon.alolan and "alolan" in self.bot.shiny_dict.get(pokemon.id, {}) and "research" in self.bot.shiny_dict.get(pokemon.id, {}).get("alolan", []):
                    shiny_str = self.bot.custom_emoji.get('shiny_chance', '\u2728') + " "
                elif str(pokemon.form).lower() in self.bot.shiny_dict.get(pokemon.id, {}) and "research" in self.bot.shiny_dict.get(pokemon.id, {}).get(str(pokemon.form).lower(), []):
                    shiny_str = self.bot.custom_emoji.get('shiny_chance', '\u2728') + " "
        if pokemon:
            reward = f"{shiny_str}{string.capwords(reward, ' ')} {pokemon.emoji}"
            invasion_embed.add_field(name=_("**Reward:**"), value=reward, inline=True)
            reward = reward.replace(pokemon.emoji, "").replace(shiny_str, "").strip()
            pkmn_types = copy.deepcopy(pokemon.types)
            pkmn_types.append('None')
            invasion_embed.set_thumbnail(url=pokemon.img_url)
            invasion_msg = f"Invasion reported by {ctx.author.mention}! Use {complete_emoji} if you completed the invasion or {expire_emoji} if the invasion has disappeared!"
        else:
            reward = "Unknown Pokemon"
            invasion_embed.add_field(name=_("**Reward:**"), value=reward, inline=True)
            invasion_msg = f"Invasion reported by {ctx.author.mention}! Use {complete_emoji} if you completed the invasion or {expire_emoji} if the invasion has disappeared or {info_emoji} to add the reward!"
        if timer:
            invasion_msg = invasion_msg.replace(f" or {expire_emoji} if the invasion has disappeared", "")
        invasion_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=ctx.author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=ctx.author.avatar_url_as(format=None, static_format='jpg', size=32))
        invasion_embed.title = _('Meowth! Click here for my directions to the invasion!')
        invasion_embed.description = f"Ask {ctx.author.name} if my directions aren't perfect!\n**Location:** {location}"
        loc_url = utils.create_gmaps_query(self.bot, location, ctx.channel, type="invasion")
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        stop_info = ""
        if gym_matching_cog:
            stop_info, location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "invasion", dupe_check=False)
            if stop_url:
                loc_url = stop_url
                invasion_embed.description = stop_info
        if not location:
            return
        pkmn_types = ["None", "None"]
        invasion_embed.url = loc_url
        invasion_embed.add_field(name=f"**{'Expires' if timer else 'Expire Estimate'}:**", value=f"{expire_time} mins {end.strftime(_('(%I:%M %p)'))}")
        invasion_embed.set_author(name="Invasion Report", icon_url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/ic_shadow.png?cache=1")
        ctx.invreportmsg = await ctx.channel.send(invasion_msg, embed=invasion_embed)
        await utils.safe_reaction(ctx.invreportmsg, complete_emoji)
        await utils.safe_reaction(ctx.invreportmsg, expire_emoji)
        if reward == "Unknown Pokemon":
            await utils.safe_reaction(ctx.invreportmsg, info_emoji)
        self.bot.guild_dict[ctx.guild.id]['invasion_dict'][ctx.invreportmsg.id] = {
            'exp':time.time() + int(expire_time)*60,
            'expedit':"delete",
            'report_message':ctx.message.id,
            'report_channel':ctx.channel.id,
            'report_author':ctx.author.id,
            'report_guild':ctx.guild.id,
            'dm_dict':dm_dict,
            'location':location,
            'url':loc_url,
            'reward':reward,
            'completed_by':[]
        }
        dm_dict = await self.send_dm_messages(ctx, reward, location, copy.deepcopy(invasion_embed), dm_dict)
        self.bot.guild_dict[ctx.guild.id]['invasion_dict'][ctx.invreportmsg.id]['dm_dict'] = dm_dict
        if pokemon:
            self.bot.guild_dict[ctx.guild.id]['invasion_dict'][ctx.invreportmsg.id]['pkmn_obj'] = str(pokemon)
        if not ctx.author.bot:
            invasion_reports = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('invasion_reports', 0) + 0.5
            self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['invasion_reports'] = invasion_reports
            if pokemon:
                invasion_reports = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('invasion_reports', 0) + 0.5
                self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['invasion_reports'] = invasion_reports

    @invasion.command(aliases=['expire'])
    @checks.allowinvasionreport()
    @commands.has_permissions(manage_channels=True)
    async def reset(self, ctx, *, report_message=None):
        """Resets all invasion reports."""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel

        # get settings
        invasion_dict = copy.deepcopy(self.bot.guild_dict[guild.id].setdefault('invasion_dict', {}))
        await utils.safe_delete(message)

        if not invasion_dict:
            return
        if report_message and int(report_message) in invasion_dict.keys():
            try:
                report_message = await channel.fetch_message(report_message)
            except:
                await utils.expire_dm_reports(self.bot, invasion_dict[report_message].get('dm_dict', {}))
                del self.bot.guild_dict[guild.id]['invasion_dict'][report_message]
                return
            await self.expire_invasion(report_message)
            return
        rusure = await channel.send(_('**Meowth!** Are you sure you\'d like to remove all invasion reports?'))
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
            for report in invasion_dict:
                try:
                    report_message = await channel.fetch_message(report)
                except:
                    await utils.expire_dm_reports(self.bot, invasion_dict[report].get('dm_dict', {}))
                    del self.bot.guild_dict[guild.id]['invasion_dict'][report]
                    return
                self.bot.loop.create_task(self.expire_invasion(report_message))
            confirmation = await channel.send(_('Invasions reset.'), delete_after=10)
            return
        else:
            return

def setup(bot):
    bot.add_cog(Invasion(bot))

def teardown(bot):
    bot.remove_cog(Invasion)
