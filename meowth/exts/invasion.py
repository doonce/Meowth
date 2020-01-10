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
            if guild.id not in list(self.bot.guild_dict.keys()):
                continue
            try:
                invasion_dict = self.bot.guild_dict[guild.id].setdefault('invasion_dict', {})
                for reportid in list(invasion_dict.keys()):
                    if invasion_dict.get(reportid, {}).get('exp', 0) <= time.time():
                        report_channel = self.bot.get_channel(invasion_dict.get(reportid, {}).get('report_channel'))
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
                            del self.bot.guild_dict[guild.id]['invasion_dict'][reportid]
                            count += 1
                            continue
                        except KeyError:
                            continue
                    to_expire = invasion_dict.get(reportid, {}).get('exp', 0) - time.time()
                    if to_expire > 10:
                        expire_list.append(to_expire)
            except Exception as e:
                print(traceback.format_exc())
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
            invasion_dict = self.bot.guild_dict[guild.id]['invasion_dict']
        except KeyError:
            invasion_dict = {}
        if message.id in invasion_dict:
            invasion_dict =  self.bot.guild_dict[guild.id]['invasion_dict'][message.id]
            if str(payload.emoji) == self.bot.custom_emoji.get('invasion_complete', 'u\U0001f1f7'):
                if user.id not in invasion_dict.get('completed_by', []):
                    if user.id != invasion_dict['report_author']:
                        invasion_dict.get('completed_by', []).append(user.id)
            elif str(payload.emoji) == self.bot.custom_emoji.get('invasion_expired', u'\U0001F4A8'):
                for reaction in message.reactions:
                    if reaction.emoji == self.bot.custom_emoji.get('invasion_expired', u'\U0001F4A8') and (reaction.count >= 3 or can_manage):
                        await self.expire_invasion(message)
            elif str(payload.emoji) == self.bot.custom_emoji.get('invasion_info', u'\U00002139\U0000fe0f'):
                ctx = await self.bot.get_context(message)
                if not ctx.prefix:
                    prefix = self.bot._get_prefix(self.bot, message)
                    ctx.prefix = prefix[-1]
                await message.remove_reaction(payload.emoji, user)
                ctx.author = user
                await self.add_invasion_info(ctx, message, user)
            elif str(payload.emoji) == self.bot.custom_emoji.get('invasion_report', u'\U0001F4E2'):
                ctx = await self.bot.get_context(message)
                ctx.author, ctx.message.author = user, user
                await message.remove_reaction(payload.emoji, user)
                return await ctx.invoke(self.bot.get_command('invasion'))
            elif str(payload.emoji) == self.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f'):
                ctx = await self.bot.get_context(message)
                await asyncio.sleep(0.25)
                await message.remove_reaction(payload.emoji, self.bot.user)
                await asyncio.sleep(0.25)
                await message.remove_reaction(payload.emoji, user)
                await ctx.invoke(self.bot.get_command("list invasions"))
                await asyncio.sleep(5)
                await utils.safe_reaction(message, payload.emoji)

    async def expire_invasion(self, message):
        guild = message.channel.guild
        channel = message.channel
        invasion_dict = copy.deepcopy(self.bot.guild_dict[guild.id]['invasion_dict'])
        author = guild.get_member(invasion_dict.get(message.id, {}).get('report_author'))
        await utils.safe_delete(message)
        try:
            user_message = await channel.fetch_message(invasion_dict[message.id]['report_message'])
            await utils.safe_delete(user_message)
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException, KeyError):
            pass
        await utils.expire_dm_reports(self.bot, invasion_dict[message.id].get('dm_dict', {}))
        invasion_bonus = invasion_dict.get(message.id, {}).get('completed_by', [])
        if len(invasion_bonus) >= 3 and author and not author.bot:
            invasion_reports = self.bot.guild_dict[message.guild.id].setdefault('trainers', {}).setdefault(author.id, {}).setdefault('reports', {}).setdefault('invasion', 0) + 1
            self.bot.guild_dict[message.guild.id]['trainers'][author.id]['reports']['invasion'] = invasion_reports
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
        reward = invasion_dict.get('reward', [])
        reward_type = invasion_dict.get('reward_type', '')
        location = invasion_dict.get('location', '')
        info_emoji = ctx.bot.custom_emoji.get('invasion_info', u'\U00002139\U0000fe0f')
        if not author:
            return
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        error = False
        success = []
        reply_msg = f"**reward <encounter>** - Current: {invasion_dict.get('reward', 'X')}\n"
        reply_msg += f"**type <grunt type>** - Current: {invasion_dict.get('reward_type', 'X')}\n"
        reply_msg += f"**gender <grunt gender>** - Current: {invasion_dict.get('gender', 'X')}\n"
        reply_msg += f"**leader <leader name>** - Current: {invasion_dict.get('leader', 'X')}\n"
        invasion_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/invasion/teamrocket.png?cache=1')
        invasion_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        while True:
            async with ctx.typing():
                invasion_embed.add_field(name=_('**Edit Invasion Info**'), value=f"Meowth! I'll help you add information to the invasion at {location}! I'll need to know what **values** you'd like to edit. Reply **cancel** to stop anytime or reply with a comma separated list of the following options `Ex: reward charizard, snorlax, gender male, type water`:\n\n{reply_msg}", inline=False)
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
                    entered_values = value_msg.clean_content.lower().split(',')
                    entered_values = [x.strip() for x in entered_values]
                    for value in entered_values:
                        value_split = value.split()
                        if "type" in value and "type" not in success:
                            if value_split[1] and value_split[1].lower() in self.bot.type_list:
                                self.bot.guild_dict[ctx.guild.id]['invasion_dict'][message.id]['reward_type'] = value_split[1]
                                success.append("type")
                            elif value_split[1] and value_split[1].lower() == "none":
                                self.bot.guild_dict[ctx.guild.id]['invasion_dict'][message.id]['reward_type'] = None
                                success.append("type")
                            else:
                                error = _('entered something invalid. Please enter a pokemon type')
                        elif "gender" in value and "gender" not in success:
                            if value_split[1] and (value_split[1] == "male" or value_split[1] == "female"):
                                self.bot.guild_dict[ctx.guild.id]['invasion_dict'][message.id]['gender'] = value_split[1]
                                success.append("gender")
                            elif value_split[1] and value_split[1].lower() == "none":
                                self.bot.guild_dict[ctx.guild.id]['invasion_dict'][message.id]['gender'] = None
                                success.append("gender")
                            else:
                                error = _('entered something invalid. Please enter male or female')
                        elif "leader" in value and "leader" not in success:
                            if value_split[1] and (value_split[1] == "arlo" or value_split[1] == "cliff" or value_split[1] == "sierra" or value_split[1] == "giovanni"):
                                self.bot.guild_dict[ctx.guild.id]['invasion_dict'][message.id]['leader'] = value_split[1]
                                success.append("leader")
                            elif value_split[1] and value_split[1].lower() == "none":
                                self.bot.guild_dict[ctx.guild.id]['invasion_dict'][message.id]['leader'] = None
                                success.append("leader")
                            else:
                                error = _('entered something invalid. Please enter arlo, cliff, sierra, or giovanni')
                        else:
                            if "reward" in value.lower() and "none" in value.lower():
                                reward = []
                                reward_type = None
                                success.append("reward")
                                continue
                            pkmn_list = value.replace('reward', '').split()
                            pkmn_list = [x.strip() for x in pkmn_list]
                            for pokemon in pkmn_list:
                                pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, pokemon)
                                if not pokemon:
                                    continue
                                pokemon.shiny = False
                                pokemon.size = None
                                pokemon.gender = None
                                pokemon.shadow = "shadow"
                                if str(pokemon) in reward:
                                    continue
                                reward.append(str(pokemon))
                            if not reward or not pkmn_list:
                                error = _("didn't enter a new pokemon")
                                break
                            elif len(reward) > 3:
                                error = _("entered too many pokemon, but the first 3 were added. Use `reward none` to clear reward")
                                break
                            elif "reward" not in success:
                                success.append("reward")
                    break
        if success:
            await self.edit_invasion_messages(ctx, message)
        else:
            error = _("didn't change anything")
        if error:
            invasion_embed.clear_fields()
            invasion_embed.add_field(name=_('**Invasion Edit Cancelled**'), value=f"Meowth! Your edit has been cancelled because you **{error}**! Retry when you're ready.", inline=False)
            if success:
                invasion_embed.set_field_at(0, name="**Invasion Edit Error**", value=f"Meowth! Your **{(', ').join(success)}** edits were successful, but others were skipped because you **{error}**! Retry when you're ready.", inline=False)
            confirmation = await channel.send(embed=invasion_embed, delete_after=10)

    async def edit_invasion_messages(self, ctx, message):
        invasion_dict = self.bot.guild_dict[ctx.guild.id]['invasion_dict'].get(message.id, {})
        reward = invasion_dict.get('reward', [])
        reward_type = invasion_dict.get('reward_type', '')
        gender = invasion_dict.get('gender', '')
        leader = invasion_dict.get('leader', '')
        dm_dict = invasion_dict.get('dm_dict', {})
        report_time = datetime.datetime.utcfromtimestamp(invasion_dict.get('report_time', time.time()))
        now_utc = datetime.datetime.utcnow()
        now_local = now_utc + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
        expire_time = invasion_dict.get('expire_time', "30")
        end_utc = report_time + datetime.timedelta(minutes=int(expire_time))
        end_local = report_time + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0), minutes=int(expire_time))
        old_embed = message.embeds[0]
        invasion_embed = discord.Embed(description=old_embed.description, title=old_embed.title, url=old_embed.url, colour=ctx.guild.me.colour).set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/invasion/teamrocket{'_male' if gender == 'male' else ''}{'_female' if gender == 'female' else ''}.png?cache=1")
        nearest_stop = invasion_dict.get('location', None)
        complete_emoji = self.bot.custom_emoji.get('invasion_complete', 'u\U0001f1f7')
        expire_emoji = self.bot.custom_emoji.get('invasion_expired', u'\U0001F4A8')
        info_emoji = ctx.bot.custom_emoji.get('invasion_info', u'\U00002139\U0000fe0f')
        report_emoji = self.bot.custom_emoji.get('invasion_report', u'\U0001F4E2')
        list_emoji = ctx.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f')
        author = ctx.guild.get_member(invasion_dict.get('report_author', None))
        if author:
            ctx.author = author
        invasion_embed.set_author(name=f"Invasion Report {' (♀)' if gender == 'female' else ''}{' (♂)' if gender == 'male' else ''}", icon_url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_shadow.png?cache=2")
        if leader:
            invasion_embed.set_author(name=f"Team Rocket Leader Report ({leader.title()})", icon_url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/item/Item_Leader_MapCompass.png?cache=2")
            invasion_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/invasion/teamrocket{'_'+leader.lower()}.png?cache=1")
            end_local = now_local.replace(hour=22, minute=0, second=0, microsecond=0)
        timer = int((end_local-now_local).total_seconds()/60)
        pokemon = None
        shiny_str = ""
        reward_str = ""
        reward_list = []
        if not reward and not reward_type:
            invasion_embed.add_field(name=_("**Possible Rewards:**"), value="Unknown Pokemon", inline=True)
        elif not reward and reward_type:
            invasion_embed.add_field(name=_("**Possible Rewards:**"), value=f"{reward_type.title()} Invasion {self.bot.config.type_id_dict[reward_type.lower()]}", inline=True)
            invasion_embed.add_field(name=_("**Weaknesses:**"), value=f"{utils.weakness_to_emoji(self.bot, utils.get_weaknesses(self.bot, [reward_type.title()]))}\u200b", inline=True)
        else:
            for pokemon in reward:
                pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, pokemon)
                if not pokemon:
                    continue
                pokemon.shiny = False
                pokemon.size = None
                pokemon.gender = None
                pokemon.shadow = "shadow"
                if pokemon.id in self.bot.shiny_dict:
                    if str(pokemon.form).lower() in self.bot.shiny_dict.get(pokemon.id, {}) and "shadow" in self.bot.shiny_dict.get(pokemon.id, {}).get(str(pokemon.form).lower(), []):
                        shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
                reward_str += f"{shiny_str}{pokemon.name.title()} {pokemon.emoji}\n"
                reward_list.append(str(pokemon))
            if not reward_list:
                invasion_embed.add_field(name=_("**Possible Rewards:**"), value="Unknown Pokemon", inline=True)
            else:
                invasion_embed.add_field(name=_("**Possible Rewards:**"), value=f"{reward_str}", inline=True)
                invasion_embed.set_thumbnail(url=pokemon.img_url)
                invasion_embed.add_field(name=_("**Weaknesses:**"), value=f"{pokemon.weakness_emoji}\u200b", inline=True)
        for field in old_embed.fields:
            if "expire" in field.name.lower():
                invasion_embed.add_field(name=field.name, value=f"{timer} mins {end_local.strftime(_('(%I:%M %p)'))}")
        if pokemon:
            invasion_msg = f"Meowth! {pokemon.name.title()} Invasion reported by {author.mention}! Details: {nearest_stop}\n\nUse {complete_emoji} if completed, {expire_emoji} if expired, {info_emoji} to edit details, {report_emoji} to report new, or {list_emoji} to list all invasions!"
        elif reward_type:
            invasion_msg = f"Meowth! {reward_type.title()} Invasion reported by {author.mention}! Details: {nearest_stop}\n\nUse {complete_emoji} if completed, {expire_emoji} if expired, {info_emoji} to edit details, {report_emoji} to report new, or {list_emoji} to list all invasions!"
        else:
            invasion_msg = f"Meowth! Invasion reported by {author.mention}! Details: {nearest_stop}\n\nUse {complete_emoji} completed, {expire_emoji} if expired, {info_emoji} to edit details, {report_emoji} to report new, or {list_emoji} to list all invasions!"
        try:
            await message.edit(content=invasion_msg, embed=invasion_embed)
        except:
            pass
        if isinstance(invasion_embed.description, discord.embeds._EmptyEmbed):
            invasion_embed.description = ""
        if "Jump to Message" not in invasion_embed.description:
            invasion_embed.description = invasion_embed.description + f"\n**Report:** [Jump to Message]({message.jump_url})"
        new_description = str(invasion_embed.description)
        for dm_user, dm_message in dm_dict.items():
            try:
                dm_user = self.bot.get_user(dm_user)
                dm_channel = dm_user.dm_channel
                if not dm_channel:
                    dm_channel = await dm_user.create_dm()
                if not dm_user or not dm_channel:
                    continue
                dm_message = await dm_channel.fetch_message(dm_message)
                if pokemon:
                    content = f"Meowth! {pokemon.name.title()} Invasion reported by {author.display_name} in {message.channel.mention}! Details: {nearest_stop}"
                elif reward_type:
                    content = f"Meowth! {reward_type.title()} Invasion reported by {author.display_name} in {message.channel.mention}! Details: {nearest_stop}"
                else:
                    content = f"Meowth! Invasion reported by {author.display_name} in {message.channel.mention}! Details: {nearest_stop}"
                invasion_embed.description = dm_message.embeds[0].description
                await dm_message.edit(content=content, embed=invasion_embed)
            except:
                pass
        invasion_embed.description = new_description
        ctx.invreportmsg = message
        dm_dict = await self.send_dm_messages(ctx, reward_list, nearest_stop, copy.deepcopy(invasion_embed), dm_dict)
        self.bot.guild_dict[ctx.guild.id]['invasion_dict'][message.id]['dm_dict'] = dm_dict
        self.bot.guild_dict[ctx.guild.id]['invasion_dict'][message.id]['exp'] = time.time() + int((end_local-now_local).total_seconds())

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
        invasion_type = None
        pokemon = None
        pkmn_list = []
        if inv_pokemon in self.bot.type_list:
            invasion_type = inv_pokemon
        elif inv_pokemon:
            for pokemon in inv_pokemon:
                pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, pokemon)
                if pokemon:
                    pkmn_list.append(pokemon)
        for trainer in self.bot.guild_dict[ctx.guild.id].get('trainers', {}):
            user_wants = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].get('alerts', {}).get('wants', [])
            user_forms = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].get('alerts', {}).get('forms', [])
            pokemon_setting = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].get('alerts', {}).get('settings', {}).get('categories', {}).get('pokemon', {}).get('invasion', True)
            user_stops = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].get('alerts', {}).get('stops', [])
            stop_setting = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].get('alerts', {}).get('settings', {}).get('categories', {}).get('pokestop', {}).get('invasion', True)
            user_types = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].get('alerts', {}).get('types', [])
            type_setting = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].get('alerts', {}).get('settings', {}).get('categories', {}).get('type', {}).get('invasion', True)
            if not any([user_wants, user_forms, pokemon_setting, user_stops, stop_setting, user_types, type_setting]):
                continue
            if not checks.dm_check(ctx, trainer, "invasion") or trainer in dm_dict:
                continue
            send_invasion = []
            if pokemon_setting or type_setting:
                for pokemon in pkmn_list:
                    pkmn_types = pokemon.types.copy()
                    pkmn_types.append("None")
                    if pokemon_setting and pokemon.id in user_wants:
                        send_invasion.append(f"Pokemon: {pokemon.name.title()}")
                    if pokemon_setting and str(pokemon) in user_forms:
                        send_invasion.append(f"Pokemon Form: {str(pokemon)}")
                    if type_setting and pkmn_types[0].lower() in user_types:
                        type_emoji = utils.parse_emoji(ctx.guild, self.bot.config.type_id_dict[pkmn_types[0].lower()])
                        send_invasion.append(f"Type: {type_emoji}")
                    if type_setting and pkmn_types[1].lower() in user_types:
                        type_emoji = utils.parse_emoji(ctx.guild, self.bot.config.type_id_dict[pkmn_types[1].lower()])
                        send_invasion.append(f"Type: {type_emoji}")
            if stop_setting and str(location).lower() in user_stops:
                send_invasion.append(f"Pokestop: {str(location).title()}")
            if type_setting and invasion_type in user_types:
                type_emoji = utils.parse_emoji(ctx.guild, self.bot.config.type_id_dict[invasion_type])
                send_invasion.append(f"Type: {type_emoji}")
            if send_invasion:
                embed.description = embed.description + f"\n**Subscription:** {(', ').join(send_invasion)}"
                try:
                    user = ctx.guild.get_member(trainer)
                    if pokemon:
                        invdmmsg = await user.send(f"{pokemon.name.title()} Invasion reported at **{location}** by {ctx.author.display_name} in {ctx.channel.mention}!", embed=embed)
                    elif invasion_type:
                        invdmmsg = await user.send(f"{invasion_type.title()} Invasion reported at **{location}** by {ctx.author.display_name} in {ctx.channel.mention}!", embed=embed)
                    else:
                        invdmmsg = await user.send(f"Invasion reported at **{location}** by {ctx.author.display_name} in {ctx.channel.mention}!", embed=embed)
                    dm_dict[user.id] = invdmmsg.id
                except Exception as e:
                    pass
                embed.description = embed.description.replace(f"\n**Subscription:** {(', ').join(send_invasion)}", "")
        return dm_dict

    @commands.group(aliases=['inv'], invoke_without_command=True, case_insensitive=True)
    @checks.allowinvasionreport()
    async def invasion(self, ctx, *, details = None):
        """Report Invasion
        Guided report method with just !invasion. If you supply arguments in one
        line, avoid commas in anything but your separations between pokestop,
        and reward. Order matters if you supply arguments.

        Usage: !invasion [pokestop name [optional URL], reward or type]
        Guided report available with just !invasion"""
        message = ctx.message
        channel = message.channel
        author = message.author
        guild = message.guild
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        exp_timestamp = (ctx.message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0), minutes=30, seconds=0)).strftime('%I:%M %p')
        error = False
        loc_url = utils.create_gmaps_query(self.bot, "", message.channel, type="invasion")
        invasion_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/invasion/teamrocket.png?cache=1')
        invasion_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        pokemon = False
        gender = None
        invasion_dict = self.bot.guild_dict[ctx.guild.id].setdefault('invasion_dict', {})
        while True:
            async with ctx.typing():
                if details:
                    invasion_split = details.rsplit(",", 2)
                    if len(invasion_split) == 1:
                        invasion_split.append([])
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
                    invasion_embed.set_field_at(0, name=invasion_embed.fields[0].name, value=_("Fantastic! Now, reply with a comma separated list of the **pokemon** Team Rocket is using at the **{location}** invasion. If you don't know the pokemon, reply with **N**, otherwise reply with as many as you know.\n\nYou can also reply with the **type** of invasion from the Team Rocket grunt's dialogue. You can reply with **cancel** to stop anytime").format(location=location), inline=False)
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
                        reward = []
                    elif rewardmsg.clean_content.lower().strip() in self.bot.type_list:
                        reward = rewardmsg.clean_content.lower().strip()
                    elif rewardmsg:
                        reward = rewardmsg.clean_content.split(',')
                        reward = [x.strip() for x in reward]
                        if len(reward) > 3:
                            error = _("entered too many pokemon")
                            break
                    break
        if not error:
            await self.send_invasion(ctx, location, reward, gender)
        else:
            invasion_embed.clear_fields()
            invasion_embed.add_field(name=_('**Invasion Report Cancelled**'), value=_("Meowth! Your report has been cancelled because you **{error}**! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await channel.send(embed=invasion_embed, delete_after=10)
            if not message.embeds:
                await utils.safe_delete(message)

    async def send_invasion(self, ctx, location, reward=None, gender=None, leader=None, timer=None):
        dm_dict = {}
        expire_time = "30"
        if timer:
            expire_time = timer
        invasion_dict = self.bot.guild_dict[ctx.guild.id].setdefault('invasion_dict', {})
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.message.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
        end = now + datetime.timedelta(minutes=int(expire_time))
        complete_emoji = self.bot.custom_emoji.get('invasion_complete', 'u\U0001f1f7')
        expire_emoji = self.bot.custom_emoji.get('invasion_expired', u'\U0001F4A8')
        info_emoji = ctx.bot.custom_emoji.get('invasion_info', u'\U00002139\U0000fe0f')
        report_emoji = self.bot.custom_emoji.get('invasion_report', u'\U0001F4E2')
        list_emoji = ctx.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f')
        react_list = [complete_emoji, expire_emoji, info_emoji, report_emoji, list_emoji]
        invasion_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/invasion/teamrocket{'_male' if gender == 'male' else ''}{'_female' if gender == 'female' else ''}.png?cache=1")
        pokemon = None
        shiny_str = ""
        reward_str = ""
        reward_list = []
        reward_type = None
        if not reward:
            reward = []
            invasion_embed.add_field(name=_("**Possible Rewards:**"), value="Unknown Pokemon", inline=True)
        elif isinstance(reward, str) and reward.lower() in self.bot.type_list:
            invasion_embed.add_field(name=_("**Possible Rewards:**"), value=f"{reward.title()} Invasion {self.bot.config.type_id_dict[reward.lower()]}", inline=True)
            invasion_embed.add_field(name=_("**Weaknesses:**"), value=f"{utils.weakness_to_emoji(self.bot, utils.get_weaknesses(self.bot, [reward.title()]))}\u200b", inline=True)
            reward = reward.strip().lower()
            reward_type = reward.strip().lower()
        else:
            for pokemon in reward:
                pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, pokemon)
                if pokemon:
                    pokemon.shiny = False
                    pokemon.shadow = "shadow"
                    if pokemon.id in self.bot.shiny_dict:
                        if str(pokemon.form).lower() in self.bot.shiny_dict.get(pokemon.id, {}) and "shadow" in self.bot.shiny_dict.get(pokemon.id, {}).get(str(pokemon.form).lower(), []):
                            shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
                    reward_str += f"{shiny_str}{pokemon.name.title()} {pokemon.emoji}\n"
                    reward_list.append(str(pokemon))
            if not reward_list:
                invasion_embed.add_field(name=_("**Possible Rewards:**"), value="Unknown Pokemon", inline=True)
            else:
                reward = reward_list
                invasion_embed.add_field(name=_("**Possible Rewards:**"), value=f"{reward_str}", inline=True)
                invasion_embed.set_thumbnail(url=pokemon.img_url)
                invasion_embed.add_field(name=_("**Weaknesses:**"), value=f"{pokemon.weakness_emoji}\u200b", inline=True)
        if pokemon:
            invasion_msg = f"Meowth! {pokemon.name.title()} Invasion reported by {ctx.author.mention}! Details: {location}\n\nUse {complete_emoji} if completed, {expire_emoji} if expired, {info_emoji} to edit details, {report_emoji} to report new, or {list_emoji} to list all invasions!"
        elif reward_type:
            invasion_msg = f"Meowth! {reward_type.title()} Invasion reported by {ctx.author.mention}! Details: {location}\n\nUse {complete_emoji} if completed, {expire_emoji} if expired, {info_emoji} to edit details, {report_emoji} to report new, or {list_emoji} to list all invasions!"
        else:
            invasion_msg = f"Meowth! Invasion reported by {ctx.author.mention}! Details: {location}\n\nUse {complete_emoji} if completed, {expire_emoji} if expired, {info_emoji} to edit details, {report_emoji} to report new, or {list_emoji} to list all invasions!"
        invasion_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=ctx.author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=ctx.author.avatar_url_as(format=None, static_format='jpg', size=32))
        invasion_embed.title = _('Meowth! Click here for my directions to the invasion!')
        invasion_embed.description = f"Ask {ctx.author.name} if my directions aren't perfect!\n**Location:** {location}"
        loc_url = utils.create_gmaps_query(self.bot, location, ctx.channel, type="invasion")
        gym_matching_cog = self.bot.cogs.get('GymMatching')
        stop_info = ""
        if gym_matching_cog:
            stop_info, location, stop_url = await gym_matching_cog.get_poi_info(ctx, location, "invasion", dupe_check=False, autocorrect=False)
            if stop_url:
                loc_url = stop_url
                invasion_embed.description = stop_info
        if not location:
            return
        invasion_embed.url = loc_url
        invasion_embed.add_field(name=f"**{'Expires' if timer else 'Expire Estimate'}:**", value=f"{expire_time} mins {end.strftime(_('(%I:%M %p)'))}")
        invasion_embed.set_author(name=f"Invasion Report {' (♀)' if gender == 'female' else ''}{' (♂)' if gender == 'male' else ''}", icon_url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/ic_shadow.png?cache=2")
        if leader:
            invasion_embed.set_author(name=f"Team Rocket Leader Report ({leader.title()})", icon_url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/item/Item_Leader_MapCompass.png?cache=2")
            invasion_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/invasion/teamrocket{'_'+leader.lower()}.png?cache=1")
        ctx.invreportmsg = await ctx.channel.send(invasion_msg, embed=invasion_embed)
        for reaction in react_list:
            await asyncio.sleep(0.25)
            await utils.safe_reaction(ctx.invreportmsg, reaction)
        self.bot.guild_dict[ctx.guild.id]['invasion_dict'][ctx.invreportmsg.id] = {
            'exp':time.time() + int(expire_time)*60,
            'expedit':"delete",
            'report_message':ctx.message.id,
            'report_channel':ctx.channel.id,
            'report_author':ctx.author.id,
            'report_guild':ctx.guild.id,
            'report_time':time.time(),
            'expire_time':expire_time,
            'dm_dict':dm_dict,
            'location':location,
            'url':loc_url,
            'reward':reward,
            'completed_by':[],
            'reward_type':reward_type,
            'leader':leader
        }
        dm_dict = await self.send_dm_messages(ctx, reward, location, copy.deepcopy(invasion_embed), dm_dict)
        self.bot.guild_dict[ctx.guild.id]['invasion_dict'][ctx.invreportmsg.id]['dm_dict'] = dm_dict
        if str(reward).lower() in self.bot.type_list:
            self.bot.guild_dict[ctx.guild.id]['invasion_dict'][ctx.invreportmsg.id]['reward'] = []
        if not ctx.author.bot:
            invasion_reports = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('reports', {}).setdefault('invasion', 0) + 1
            self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['reports']['invasion'] = invasion_reports

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
        if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', u'\U0000274e'):
            await utils.safe_delete(rusure)
            confirmation = await channel.send(_('Manual reset cancelled.'), delete_after=10)
            return
        elif res.emoji == self.bot.custom_emoji.get('answer_yes', u'\U00002705'):
            await utils.safe_delete(rusure)
            async with ctx.typing():
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
