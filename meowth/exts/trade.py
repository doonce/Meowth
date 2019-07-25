import asyncio
import functools
import datetime
import time
import logging
import copy

import discord
from discord.ext import commands, tasks

from meowth import checks

from meowth.exts import pokemon as pkmn_class
from meowth.exts import utilities as utils

logger = logging.getLogger("meowth")

class Trading(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.trade_cleanup.start()

    def cog_unload(self):
        self.trade_cleanup.cancel()

    @tasks.loop(seconds=86400)
    async def trade_cleanup(self, loop=True):
        logger.info('------ BEGIN ------')
        yes_emoji = self.bot.custom_emoji.get('trade_complete', '\u2611')
        no_emoji = self.bot.custom_emoji.get('trade_stop', '\u23f9')
        for guild in list(self.bot.guilds):
            trade_dict = self.bot.guild_dict[guild.id].setdefault('trade_dict', {})
            for listing_id in trade_dict:
                if trade_dict[listing_id].get('exp', 0) <= time.time():
                    trade_channel = self.bot.get_channel(trade_dict[listing_id].get('report_channel_id'))
                    if trade_channel:
                        if trade_dict[listing_id]['status'] == "active" and not trade_dict[listing_id].get('active_check', None):
                            lister = guild.get_member(trade_dict[listing_id]['lister_id'])
                            try:
                                listing_msg = await trade_channel.fetch_message(listing_id)
                            except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                                await self.close_trade(guild.id, listing_id)
                            if not lister:
                                await self.close_trade(guild.id, listing_id)
                                continue
                            embed = listing_msg.embeds[0]
                            embed.description = f"**Trade:** [Jump to Message]({listing_msg.jump_url})"
                            active_check_msg = await lister.send(f"Meowth... Is this trade listing still active? React with {yes_emoji} to extend trade for 30 more days or react with {no_emoji} to cancel trade. I'll automatically cancel it in seven days if I don't hear from you.", embed=embed)
                            self.bot.guild_dict[guild.id]['trade_dict'][listing_id]['active_check'] = active_check_msg.id
                            self.bot.guild_dict[guild.id]['trade_dict'][listing_id]['exp'] = time.time() + 7*24*60*60
                            await utils.safe_reaction(active_check_msg, yes_emoji)
                            await utils.safe_reaction(active_check_msg, no_emoji)
                        elif trade_dict[listing_id]['status'] == "active" and trade_dict[listing_id].get('active_check', None):
                            dm_dict = {trade_dict[listing_id]['lister_id'] : trade_dict[listing_id]['active_check']}
                            await utils.expire_dm_reports(self.bot, dm_dict)
                            await self.cancel_trade(guild.id, listing_id)
                        elif trade_dict[listing_id]['status'] == "accepted" and not trade_dict[listing_id].get('active_check', None):
                            lister = guild.get_member(trade_dict[listing_id]['lister_id'])
                            buyer = guild.get_member(trade_dict[listing_id]['accepted']['buyer_id'])
                            try:
                                listing_msg = await trade_channel.fetch_message(listing_id)
                            except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                                await self.close_trade(guild_id, listing_id)
                            embed = listing_msg.embeds[0]
                            embed.description = f"**Trade:** [Jump to Message]({listing_msg.jump_url})"
                            active_check_msg = await lister.send(f"Meowth... Did you complete this trade with {buyer.display_name}? React with {yes_emoji} to extend trade for 30 more days or react with {no_emoji} to confirm trade. I'll automatically cancel it in seven days if I don't hear from you.", embed=embed)
                            self.bot.guild_dict[guild.id]['trade_dict'][listing_id]['active_check'] = active_check_msg.id
                            self.bot.guild_dict[guild.id]['trade_dict'][listing_id]['exp'] = time.time() + 7*24*60*60
                            await utils.safe_reaction(active_check_msg, yes_emoji)
                            await utils.safe_reaction(active_check_msg, no_emoji)
                        elif trade_dict[listing_id]['status'] == "accepted" and trade_dict[listing_id].get('active_check', None):
                            dm_dict = {trade_dict[listing_id]['lister_id'] : trade_dict[listing_id]['active_check']}
                            await utils.expire_dm_reports(self.bot, dm_dict)
                            dm_dict = {
                                trade_dict[listing_id]['lister_id'] : trade_dict[listing_id]['accepted']['lister_msg'],
                                trade_dict[listing_id]['accepted']['buyer_id'] : trade_dict[listing_id]['accepted']['buyer_msg'],
                            }
                            await utils.expire_dm_reports(self.bot, dm_dict)
                            await self.cancel_trade(guild.id, listing_id)
        # save server_dict changes after cleanup
        logger.info('SAVING CHANGES')
        try:
            await self.bot.save
        except Exception as err:
            logger.info('SAVING FAILED' + err)
            pass
        logger.info(f"------ END ------")
        if not loop:
            return

    @trade_cleanup.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        channel = self.bot.get_channel(payload.channel_id)
        try:
            user = self.bot.get_user(payload.user_id)
        except AttributeError:
            return
        if not channel:
            channel = user.dm_channel
            if not channel:
                channel = await user.create_dm()
            if not channel:
                return
        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.errors.NotFound, AttributeError, discord.Forbidden):
            return
        emoji = payload.emoji.name
        active_check_dict = {}
        offer_dict = {}
        accepted_dict = {}
        if user.bot:
            return
        for guildid in self.bot.guild_dict.keys():
            guild = self.bot.get_guild(guildid)
            if message.guild and message.channel.id not in self.bot.guild_dict[guild.id]['configure_dict']['trade']['report_channels']:
                continue
            trade_dict = self.bot.guild_dict[guild.id]['trade_dict']
            for listing_id in trade_dict:
                if trade_dict[listing_id].get("active_check", None):
                    active_check_dict[trade_dict[listing_id]['active_check']] = {"listing_id":listing_id, "guild_id":guildid}
                if trade_dict[listing_id].get("accepted", {}):
                    accepted_dict[trade_dict[listing_id]['accepted']['lister_msg']] = {"listing_id":listing_id, "guild_id":guildid, "buyer_id":trade_dict[listing_id]['accepted']['buyer_id']}
                    accepted_dict[trade_dict[listing_id]['accepted']['buyer_msg']] = {"listing_id":listing_id, "guild_id":guildid, "buyer_id":trade_dict[listing_id]['accepted']['buyer_id']}
                if trade_dict[listing_id].get("offers", {}):
                    for offer in trade_dict[listing_id]['offers']:
                        offer_dict[trade_dict[listing_id]['offers'][offer]['lister_msg']] = {"listing_id":listing_id, "guild_id":guildid, "buyer_id":offer}
        if message.guild:
            trade_dict = self.bot.guild_dict[message.guild.id]['trade_dict']
            if message.id in trade_dict.keys():
                emoji_check = ['\u20e3' in emoji, emoji == self.bot.custom_emoji.get('trade_stop', '\u23f9')]
                if not any(emoji_check):
                    return
                if user.id != trade_dict[message.id]['lister_id'] and '\u20e3' in emoji:
                    wanted_pokemon = [await pkmn_class.Pokemon.async_get_pokemon(self.bot, want) for want in trade_dict[message.id]['wanted_pokemon'].split('\n')]
                    i = int(emoji[0])
                    offer = wanted_pokemon[i-1]
                    await self.make_offer(message.guild.id, message.id, user.id, offer)
                elif payload.user_id == trade_dict[message.id]['lister_id'] and emoji == self.bot.custom_emoji.get('trade_stop', '\u23f9'):
                    await self.cancel_trade(message.guild.id, message.id)
        elif message.id in active_check_dict.keys():
            guild = self.bot.get_guild(active_check_dict[message.id]['guild_id'])
            listing_id = active_check_dict[message.id]['listing_id']
            trade_dict = self.bot.guild_dict[guild.id]['trade_dict'][listing_id]
            if emoji == self.bot.custom_emoji.get('trade_complete', '\u2611'):
                self.bot.guild_dict[guild.id]['trade_dict'][listing_id]['exp'] = time.time() + 30*24*60*60
                self.bot.guild_dict[guild.id]['trade_dict'][listing_id]['active_check'] = None
            elif emoji == self.bot.custom_emoji.get('trade_stop', '\u23f9'):
                if trade_dict['status'] == "accepted":
                    dm_dict = {
                        trade_dict['lister_id'] : trade_dict['accepted']['lister_msg'],
                        trade_dict['accepted']['buyer_id'] : trade_dict['accepted']['buyer_msg'],
                    }
                    await utils.expire_dm_reports(self.bot, dm_dict)
                await self.cancel_trade(guild.id, listing_id)
            await message.delete()
        elif message.id in offer_dict.keys():
            guild = self.bot.get_guild(offer_dict[message.id]['guild_id'])
            if emoji == self.bot.custom_emoji.get('trade_accept', '\u2705'):
                await self.accept_offer(guild.id, offer_dict[message.id]['listing_id'], offer_dict[message.id]['buyer_id'])
            elif emoji == self.bot.custom_emoji.get('trade_reject', '\u274e'):
                await self.reject_offer(guild.id, offer_dict[message.id]['listing_id'], offer_dict[message.id]['buyer_id'])
            await message.delete()
        elif message.id in accepted_dict.keys():
            guild = self.bot.get_guild(accepted_dict[message.id]['guild_id'])
            trade_dict = self.bot.guild_dict[guild.id]['trade_dict'][accepted_dict[message.id]['listing_id']]
            if emoji == self.bot.custom_emoji.get('trade_complete', '\u2611'):
                await self.confirm_trade(guild.id, accepted_dict[message.id]['listing_id'], user.id)
            elif emoji == self.bot.custom_emoji.get('trade_stop', '\u23f9'):
                if user.id == trade_dict['lister_id']:
                    await self.reject_offer(guild.id, accepted_dict[message.id]['listing_id'], accepted_dict[message.id]['buyer_id'])
                else:
                    await self.withdraw_offer(guild.id, accepted_dict[message.id]['listing_id'], accepted_dict[message.id]['buyer_id'])
                    dm_dict = {trade_dict['lister_id'] : trade_dict['accepted']['lister_msg']}
                    await utils.expire_dm_reports(self.bot, dm_dict)
            await message.delete()

    async def make_offer(self, guild_id, listing_id, buyer_id, pkmn):
        guild = self.bot.get_guild(guild_id)
        trade_dict = self.bot.guild_dict[guild.id]['trade_dict'][listing_id]
        listing_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, trade_dict['offered_pokemon'])
        buyer_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, pkmn)
        buyer = guild.get_member(buyer_id)
        lister = guild.get_member(trade_dict['lister_id'])
        offer_embed = discord.Embed(colour=guild.me.colour)
        offer_embed.set_author(name="Pokemon Trade Offer - {}".format(buyer.display_name), icon_url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/trade_icon_small.png")
        offer_embed.add_field(name="You Offered", value=str(listing_pokemon), inline=True)
        offer_embed.add_field(name="They Offer", value=str(buyer_pokemon), inline=True)
        offer_embed.set_footer(text=f"Offered by @{buyer.display_name}", icon_url=buyer.avatar_url_as(format=None, static_format='png', size=256))
        offer_embed.set_thumbnail(url=buyer_pokemon.img_url)
        accept_emoji = self.bot.custom_emoji.get('trade_accept', '\u2705')
        reject_emoji = self.bot.custom_emoji.get('trade_reject', '\u274e')
        offermsg = await lister.send(f"Meowth! {buyer.display_name} offers to trade their {str(pkmn)} for your {str(listing_pokemon)}! React with {accept_emoji} to accept the offer or {reject_emoji} to reject it!", embed=offer_embed)
        self.bot.guild_dict[guild.id]['trade_dict'][listing_id]['offers'][buyer_id] = {
            "offer":str(buyer_pokemon),
            "lister_msg": offermsg.id
        }
        await utils.safe_reaction(offermsg, self.bot.custom_emoji.get('trade_accept', '\u2705'))
        await utils.safe_reaction(offermsg, self.bot.custom_emoji.get('trade_reject', '\u274e'))

    async def accept_offer(self, guild_id, listing_id, buyer_id):
        guild = self.bot.get_guild(guild_id)
        trade_dict = self.bot.guild_dict[guild.id]['trade_dict'][listing_id]
        if trade_dict['status'] == "active":
            buyer = guild.get_member(buyer_id)
            lister = guild.get_member(trade_dict['lister_id'])
            channel = self.bot.get_channel(trade_dict['report_channel_id'])
            try:
                listing_msg = await channel.fetch_message(listing_id)
            except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                await self.close_trade(guild_id, listing_id)
            offered_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, trade_dict['offered_pokemon'])
            wanted_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, trade_dict['offers'][buyer_id]['offer'])
            complete_emoji = self.bot.custom_emoji.get('trade_complete', '\u2611')
            cancel_emoji = self.bot.custom_emoji.get('trade_stop', '\u23f9')
            acceptedmsg = f"Meowth! {lister.display_name} has agreed to trade their {offered_pokemon} for {buyer.display_name}'s {wanted_pokemon}. React with {complete_emoji} when the trade has been completed! To reject or cancel this offer, react with {cancel_emoji}"
            special_check = [offered_pokemon.shiny, offered_pokemon.legendary, wanted_pokemon.shiny, wanted_pokemon.legendary]
            if any(special_check):
                acceptedmsg += "\n\nThis is a Special Trade! These can only be completed once per day and can cost up to 1 million stardust! Significant discounts can be earned by leveling up your friendship before the trade is made!"
            tradermsg = await buyer.send(acceptedmsg)
            listermsg = await lister.send(acceptedmsg)
            self.bot.guild_dict[guild.id]['trade_dict'][listing_id]['status'] = "accepted"
            self.bot.guild_dict[guild.id]['trade_dict'][listing_id]['accepted'] = {"buyer_id":buyer_id, "lister_msg":listermsg.id, "buyer_msg":tradermsg.id, "lister_confirm":False, "buyer_confirm":False}
            await utils.safe_reaction(tradermsg, self.bot.custom_emoji.get('trade_complete', '\u2611'))
            await utils.safe_reaction(tradermsg, self.bot.custom_emoji.get('trade_stop', '\u23f9'))
            await utils.safe_reaction(listermsg, self.bot.custom_emoji.get('trade_complete', '\u2611'))
            await utils.safe_reaction(listermsg, self.bot.custom_emoji.get('trade_stop', '\u23f9'))
            for offerid in trade_dict['offers'].keys():
                if offerid != buyer_id:
                    reject = guild.get_member(offerid)
                    try:
                        await reject.send(f"Meowth... {lister.display_name} accepted a competing offer for their {offered_pokemon}.")
                    except discord.HTTPException:
                        pass
            await listing_msg.edit(content=f"Meowth! {lister.display_name} has accepted an offer!")
            await listing_msg.clear_reactions()

    async def reject_offer(self, guild_id, listing_id, buyer_id):
        guild = self.bot.get_guild(guild_id)
        trade_dict = self.bot.guild_dict[guild.id]['trade_dict'][listing_id]
        buyer = guild.get_member(buyer_id)
        lister = guild.get_member(trade_dict['lister_id'])
        channel = self.bot.get_channel(trade_dict['report_channel_id'])
        try:
            listing_msg = await channel.fetch_message(listing_id)
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
            await self.close_trade(guild_id, listing_id)
        offered_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, trade_dict['offered_pokemon'])
        wanted_pokemon = [await pkmn_class.Pokemon.async_get_pokemon(self.bot, want) for want in trade_dict['wanted_pokemon'].split('\n')]
        await buyer.send(f"Meowth... {lister.display_name} rejected your offer for their {offered_pokemon}.")
        cancel_emoji = self.bot.custom_emoji.get('trade_stop', '\u23f9')
        offer_str = f"Meowth! {lister.display_name} offers a {str(offered_pokemon)} up for trade!"
        instructions = "React to this message to make an offer!"
        cancel_inst = f"{lister.display_name} may cancel the trade with {cancel_emoji}"
        codemsg = ""
        if lister.id in self.bot.guild_dict[guild.id].get('trainers', {}):
            trainercode = self.bot.guild_dict[guild.id]['trainers'][lister.id].get('trainercode', None)
            if trainercode:
                codemsg += f"{lister.display_name}'s trainer code is: **{trainercode}**"
        await listing_msg.edit(content=f"{offer_str}\n\n{instructions}\n\n{cancel_inst}\n\n{codemsg}")
        for i in range(len(wanted_pokemon)):
            await utils.safe_reaction(listing_msg, f'{i+1}\u20e3')
        await utils.safe_reaction(listing_msg, self.bot.custom_emoji.get('trade_stop', '\u23f9'))
        del trade_dict['offers'][buyer_id]
        self.bot.guild_dict[guild.id]['trade_dict'][listing_id]['status'] = "active"

    async def withdraw_offer(self, guild_id, listing_id, buyer_id):
        guild = self.bot.get_guild(guild_id)
        trade_dict = self.bot.guild_dict[guild.id]['trade_dict'][listing_id]
        buyer = guild.get_member(buyer_id)
        lister = guild.get_member(trade_dict['lister_id'])
        channel = self.bot.get_channel(trade_dict['report_channel_id'])
        try:
            listing_msg = await channel.fetch_message(listing_id)
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
            await self.close_trade(guild_id, listing_id)
        offered_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, trade_dict['offered_pokemon'])
        wanted_pokemon = [await pkmn_class.Pokemon.async_get_pokemon(self.bot, want) for want in trade_dict['wanted_pokemon'].split('\n')]
        buyer_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, trade_dict['offers'][buyer_id]['offer'])
        cancel_emoji = self.bot.custom_emoji.get('trade_stop', '\u23f9')
        await lister.send(f"Meowth... {buyer.display_name} withdrew their trade offer of {str(buyer_pokemon)}.")
        offer_str = f"Meowth! {lister.display_name} offers a {str(offered_pokemon)} up for trade!"
        instructions = "React to this message to make an offer!"
        cancel_inst = f"{lister.display_name} may cancel the trade with {cancel_emoji}"
        codemsg = ""
        if lister.id in self.bot.guild_dict[guild.id].get('trainers', {}):
            trainercode = self.bot.guild_dict[guild.id]['trainers'][lister.id].get('trainercode', None)
            if trainercode:
                codemsg += f"{lister.display_name}'s trainer code is: **{trainercode}**"
        await listing_msg.edit(content=f"{offer_str}\n\n{instructions}\n\n{cancel_inst}\n\n{codemsg}")
        for i in range(len(wanted_pokemon)):
            await utils.safe_reaction(listing_msg, f'{i+1}\u20e3')
        await utils.safe_reaction(listing_msg, self.bot.custom_emoji.get('trade_stop', '\u23f9'))
        del trade_dict['offers'][buyer_id]
        self.bot.guild_dict[guild.id]['trade_dict'][listing_id]['status'] = "active"

    async def cancel_trade(self, guild_id, listing_id):
        trade_dict = self.bot.guild_dict[guild_id]['trade_dict'].get(listing_id, None)
        if not trade_dict:
            try:
                del self.bot.guild_dict[guild_id]['trade_dict'][listing_id]
            except (KeyError, discord.HTTPException):
                pass
            return
        guild = self.bot.get_guild(guild_id)
        offered_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, trade_dict['offered_pokemon'])
        lister = guild.get_member(trade_dict['lister_id'])
        for offerid in trade_dict['offers']:
            reject = guild.get_member(offerid)
            await reject.send(f"Meowth... {lister.display_name} canceled their trade offer of {str(offered_pokemon)}")
            await utils.expire_dm_reports(self.bot, {lister.id: trade_dict['offers'][offerid]['lister_msg']})
        await self.close_trade(guild_id, listing_id)

    async def confirm_trade(self, guild_id, listing_id, confirm_id):
        guild = self.bot.get_guild(guild_id)
        trade_dict = self.bot.guild_dict[guild_id]['trade_dict'][listing_id]
        channel = self.bot.get_channel(trade_dict['report_channel_id'])
        try:
            listing_msg = await channel.fetch_message(listing_id)
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
            await self.close_trade(guild_id, listing_id)
        lister = guild.get_member(trade_dict['lister_id'])
        lister_confirm = trade_dict['accepted']['lister_confirm']
        buyer = guild.get_member(trade_dict['accepted']['buyer_id'])
        buyer_confirm = trade_dict['accepted']['buyer_confirm']
        if not lister_confirm and confirm_id == lister.id:
            self.bot.guild_dict[guild_id]['trade_dict'][listing_id]['accepted']['lister_confirm'] = True
            lister_confirm = True
        if not buyer_confirm and confirm_id == buyer.id:
            self.bot.guild_dict[guild_id]['trade_dict'][listing_id]['accepted']['buyer_confirm'] = True
            buyer_confirm = True
        if buyer_confirm and lister_confirm:
            await listing_msg.edit(content='Meowth! This trade has been completed!', embed=None)
            await asyncio.sleep(5)
            await self.close_trade(guild_id, listing_id)

    async def close_trade(self, guild_id, listing_id):
        try:
            trade_dict = self.bot.guild_dict[guild_id]['trade_dict'][listing_id]
            channel = self.bot.get_channel(trade_dict['report_channel_id'])
        except KeyError:
            pass
        try:
            listing_msg = await channel.fetch_message(listing_id)
            await utils.safe_delete(listing_msg)
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
            pass
        try:
            del self.bot.guild_dict[guild_id]['trade_dict'][listing_id]
        except (KeyError, discord.HTTPException):
            pass

    @commands.command()
    @checks.allowtrade()
    async def trade(self, ctx, *, offered_pokemon=''):
        """Create a trade listing."""
        await utils.safe_delete(ctx.message)
        trade_dict = self.bot.guild_dict[ctx.guild.id].setdefault('trade_dict', {})
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[ctx.channel.guild.id]['configure_dict']['settings']['offset'])).strftime(_('%I:%M %p (%H:%M)'))
        error = False
        details = None
        all_offered = offered_pokemon.split(',')
        all_offered = [x.strip() for x in all_offered]
        for index, item in enumerate(all_offered):
            pokemon, __ = await pkmn_class.Pokemon.ask_pokemon(ctx, item)
            all_offered[index] = pokemon
        all_offered = [x for x in all_offered if x]
        preview_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/pogo_trading_icon.png?cache=1')
        preview_embed.set_footer(text=f"Listed by @{ctx.author.display_name} - {timestamp}", icon_url=ctx.author.avatar_url_as(format=None, static_format='png', size=256))
        async def error_msg(e):
            preview_embed.clear_fields()
            preview_embed.add_field(name=_('**Trade Listing Cancelled**'), value=_("Meowth! Your listing has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await ctx.send(embed=preview_embed, delete_after=10)
        while True:
            async with ctx.typing():
                def check(m):
                    return m.author == ctx.author and m.channel == ctx.channel
                if not all_offered:
                    preview_embed.add_field(name=_('**New Trade Listing**'), value=f"Meowth! I'll help you list a new trade! What pokemon are you wanting to list for trade? Reply with your **pokemon** or reply with **cancel** to cancel.\n\nYour **pokemon** can contain any forms, shiny, or gender. I'll try to match it as close as possible.", inline=False)
                    trade_listing = await ctx.send(embed=preview_embed)
                    try:
                        listing_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        listing_msg = None
                    await utils.safe_delete(trade_listing)
                    if not listing_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(listing_msg)
                    if listing_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the listing")
                        await error_msg(error)
                        return
                    elif listing_msg:
                        all_offered = listing_msg.clean_content.split(',')
                        all_offered = [x.strip() for x in all_offered]
                        for index, item in enumerate(all_offered):
                            pokemon, __ = await pkmn_class.Pokemon.ask_pokemon(ctx, item)
                            all_offered[index] = pokemon
                        all_offered = [x for x in all_offered if x]
                        if not all_offered:
                            error = _("entered something invalid")
                            await error_msg(error)
                            return
                for offered_pokemon in all_offered:
                    preview_embed.clear_fields()
                    preview_embed.set_thumbnail(url=offered_pokemon.img_url)
                    preview_embed.add_field(name=f"New Trade Listing", value=f"What pokemon are you willing to accept in exchange for your {str(offered_pokemon)}?\n\nList up to 9 pokemon in a comma separated list, reply with **ask** to create an open trade, or reply with **cancel** to cancel this listing.{' Reply with **stop** to cancel all listed trades.' if len(all_offered) > 1 else ''}", inline=False)
                    want_wait = await ctx.send(embed=preview_embed)
                    try:
                        want_reply = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        want_reply = None
                    await utils.safe_delete(want_wait)
                    if not want_reply:
                        error = _("took too long to respond")
                        await error_msg(error)
                        return
                    else:
                        await utils.safe_delete(want_reply)
                    if want_reply.clean_content.lower() == "cancel":
                        error = _("cancelled the listing")
                        await error_msg(error)
                        continue
                    elif want_reply.clean_content.lower() == "stop":
                        error = _("cancelled the listing")
                        await error_msg(error)
                        return
                    wanted_pokemon = want_reply.content.lower().split(',')
                    if len(wanted_pokemon) > 9:
                        error = _("entered more than 9 pokemon")
                        await error_msg(error)
                        continue
                    if "ask" in wanted_pokemon:
                        wanted_pokemon = "open trade"
                    else:
                        wanted_pokemon_list = []
                        for pkmn in wanted_pokemon:
                            pkmn = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, pkmn)
                            if pkmn and str(pkmn) not in wanted_pokemon_list:
                                wanted_pokemon_list.append(str(pkmn))
                        wanted_pokemon = wanted_pokemon_list
                    if not wanted_pokemon:
                        error = _("entered something invalid")
                        await error_msg(error)
                        return
                    preview_embed.set_field_at(0, name=preview_embed.fields[0].name, value=f"Great! Now, would you like to add some **details** to your trade? This can be something like 'My offer has a legacy moveset, I'm looking for a great league trade. Trade is negotiable.'\n\nReply with your **details** to add them, reply with **N** to list without any details, or reply with **cancel** to cancel this listing.{' Reply with **stop** to cancel all listed trades.' if len(all_offered) > 1 else ''}", inline=False)
                    details_want = await ctx.send(embed=preview_embed)
                    try:
                        details_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        details_msg = None
                    await utils.safe_delete(details_want)
                    if not details_msg:
                        details = None
                    else:
                        await utils.safe_delete(details_msg)
                    if details_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the listing")
                        await error_msg(error)
                        continue
                    elif want_reply.clean_content.lower() == "stop":
                        error = _("cancelled the listing")
                        await error_msg(error)
                        return
                    elif details_msg.clean_content.lower() == "n":
                        details = None
                    elif details_msg:
                        details = details_msg.clean_content
                    if "open trade" not in wanted_pokemon:
                        wanted_pokemon = [f'{i+1}\u20e3: {pkmn}' for i, pkmn in enumerate(wanted_pokemon)]
                        wanted_pokemon = '\n'.join(wanted_pokemon)
                    else:
                        wanted_pokemon = "Open Trade (DM User)"
                    trade_embed = discord.Embed(colour=ctx.guild.me.colour)
                    trade_embed.set_author(name="Pokemon Trade - {}".format(ctx.author.display_name), icon_url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/trade_icon_small.png")
                    trade_embed.add_field(name="Wants", value=wanted_pokemon, inline=True)
                    trade_embed.add_field(name="Offers", value=str(offered_pokemon), inline=True)
                    if details:
                        trade_embed.add_field(name="Details", value=details, inline=False)
                    trade_embed.set_footer(text=f"Listed by @{ctx.author.display_name} - {timestamp}", icon_url=ctx.author.avatar_url_as(format=None, static_format='png', size=256))
                    trade_embed.set_thumbnail(url=offered_pokemon.img_url)
                    offered_pokemon_str = f"Meowth! {ctx.author.mention} offers a {str(offered_pokemon)} up for trade!"
                    if "open trade" not in wanted_pokemon.lower():
                        instructions = "React to this message to make an offer!"
                    else:
                        instructions = f"DM {ctx.author.display_name} to make an offer!"
                    codemsg = ""
                    if ctx.author.id in ctx.bot.guild_dict[ctx.guild.id].get('trainers', {}):
                        trainercode = ctx.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id].get('trainercode', None)
                        if trainercode:
                            codemsg += f"{ctx.author.display_name}'s trainer code is: **{trainercode}**"
                    cancel_inst = f"{ctx.author.display_name} may cancel the trade with :stop_button:"
                    trade_msg = await ctx.send(f"{offered_pokemon_str}\n\n{instructions}\n\n{cancel_inst}\n\n{codemsg}", embed=trade_embed)
                    if "open trade" not in wanted_pokemon.lower():
                        for i in range(len(wanted_pokemon.split('\n'))):
                            await utils.safe_reaction(trade_msg, f'{i+1}\u20e3')
                    await utils.safe_reaction(trade_msg, ctx.bot.custom_emoji.get('trade_stop', '\u23f9'))
                    ctx.bot.guild_dict[ctx.guild.id]['trade_dict'][trade_msg.id] = {
                        'exp':time.time() + 30*24*60*60,
                        'status':"active",
                        'lister_id': ctx.author.id,
                        'report_channel_id': ctx.channel.id,
                        'report_channel':ctx.channel.id,
                        'guild_id': ctx.guild.id,
                        'report_guild':ctx.guild.id,
                        'wanted_pokemon': wanted_pokemon,
                        'offered_pokemon': str(offered_pokemon),
                        'offers':{}
                    }
                break

def setup(bot):
    bot.add_cog(Trading(bot))

def teardown(bot):
    bot.remove_cog(Trading)
