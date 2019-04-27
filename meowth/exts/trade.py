import asyncio
import functools

import discord
from discord.ext import commands

from meowth import checks

from meowth.exts import pokemon as pkmn_class
from meowth.exts import utilities as utils

class Trade:

    icon_url = ("https://raw.githubusercontent.com/doonce/Meowth/"
                "Rewrite/images/misc/trade_icon_small.png")

    __slots__ = [
        'bot', '_data', 'lister_id', 'listing_id', 'report_channel_id',
        'guild_id', 'offers']

    def __init__(self, bot, lister_id, message_id, channel_id, guild_id,
                 wanted_pokemon, offered_pokemon):
        self.bot = bot
        trade_dict = bot.guild_dict[guild_id].setdefault('trade_dict', {})
        trade_channel_data = trade_dict.setdefault(channel_id, {})
        if wanted_pokemon == "open trade":
            wanted = ["Open Trade (DM User)"]
        else:
            wanted = [str(want) for want in wanted_pokemon]
        trade_channel_data[message_id] = {
            'lister_id'         : lister_id,
            'report_channel_id' : channel_id,
            'guild_id'          : guild_id,
            'wanted_pokemon'    : wanted,
            'offered_pokemon'   : str(offered_pokemon),
            'offers'            : {}
        }
        self._data = trade_channel_data[message_id]
        self.lister_id = self._data['lister_id']
        self.listing_id = message_id
        self.report_channel_id = self._data['report_channel_id']
        self.guild_id = self._data['guild_id']
        self.offers = self._data['offers']

<<<<<<< HEAD
    async def trade_cleanup(self, loop=True):
        while True:
            await self.bot.wait_until_ready()
            logger.info('------ BEGIN ------')
            guilddict_temp = copy.deepcopy(self.bot.guild_dict)
            yes_emoji = self.bot.config.get('trade_complete', '\u2611')
            no_emoji = self.bot.config.get('trade_stop', '\u23f9')
            for guildid in guilddict_temp.keys():
                guild = self.bot.get_guild(guildid)
                trade_dict = guilddict_temp[guild.id].setdefault('trade_dict', {})
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
                await self.bot.save()
            except Exception as err:
                logger.info('SAVING FAILED' + err)
                pass
            logger.info(f"------ END ------")
            if not loop:
                return
            await asyncio.sleep(86400)
            continue

    @commands.Cog.listener()
=======
>>>>>>> parent of 28e4680b... Complete rewrite of trade. See description.
    async def on_raw_reaction_add(self, payload):

        emoji = payload.emoji.name
        # ignore if not relevant to this trade object
        if payload.message_id != self.listing_id:
            return
<<<<<<< HEAD
        for guildid in self.bot.guild_dict.keys():
            guild = self.bot.get_guild(guildid)
            if message.guild and message.channel.id not in self.bot.guild_dict[guild.id]['configure_dict']['trade']['report_channels']:
                return
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
                emoji_check = ['\u20e3' in emoji, emoji == self.bot.config.get('trade_stop', '\u23f9')]
                if not any(emoji_check):
                    return
                if user.id != trade_dict[message.id]['lister_id'] and '\u20e3' in emoji:
                    wanted_pokemon = [pkmn_class.Pokemon.get_pokemon(self.bot, want) for want in trade_dict[message.id]['wanted_pokemon'].split('\n')]
                    i = int(emoji[0])
                    offer = wanted_pokemon[i-1]
                    await self.make_offer(message.guild.id, message.id, user.id, offer)
                elif payload.user_id == trade_dict[message.id]['lister_id'] and emoji == self.bot.config.get('trade_stop', '\u23f9'):
                    await self.cancel_trade(message.guild.id, message.id)
        elif message.id in active_check_dict.keys():
            guild = self.bot.get_guild(active_check_dict[message.id]['guild_id'])
            listing_id = active_check_dict[message.id]['listing_id']
            trade_dict = self.bot.guild_dict[guild.id]['trade_dict'][listing_id]
            if emoji == self.bot.config.get('trade_complete', '\u2611'):
                self.bot.guild_dict[guild.id]['trade_dict'][listing_id]['exp'] = time.time() + 30*24*60*60
                self.bot.guild_dict[guild.id]['trade_dict'][listing_id]['active_check'] = None
            elif emoji == self.bot.config.get('trade_stop', '\u23f9'):
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
            if emoji == self.bot.config.get('trade_accept', '\u2705'):
                await self.accept_offer(guild.id, offer_dict[message.id]['listing_id'], offer_dict[message.id]['buyer_id'])
            elif emoji == self.bot.config.get('trade_reject', '\u274e'):
                await self.reject_offer(guild.id, offer_dict[message.id]['listing_id'], offer_dict[message.id]['buyer_id'])
            await message.delete()
        elif message.id in accepted_dict.keys():
            guild = self.bot.get_guild(accepted_dict[message.id]['guild_id'])
            trade_dict = self.bot.guild_dict[guild.id]['trade_dict'][accepted_dict[message.id]['listing_id']]
            if emoji == self.bot.config.get('trade_complete', '\u2611'):
                await self.confirm_trade(guild.id, accepted_dict[message.id]['listing_id'], user.id)
            elif emoji == self.bot.config.get('trade_stop', '\u23f9'):
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
        listing_pokemon = pkmn_class.Pokemon.get_pokemon(self.bot, trade_dict['offered_pokemon'])
        buyer_pokemon = pkmn_class.Pokemon.get_pokemon(self.bot, pkmn)
        buyer = guild.get_member(buyer_id)
        lister = guild.get_member(trade_dict['lister_id'])
        offer_embed = discord.Embed(colour=guild.me.colour)
        offer_embed.set_author(name="Pokemon Trade Offer - {}".format(buyer.display_name), icon_url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/trade_icon_small.png")
        offer_embed.add_field(name="You Offered", value=str(listing_pokemon), inline=True)
        offer_embed.add_field(name="They Offer", value=str(buyer_pokemon), inline=True)
        offer_embed.set_footer(text=f"Offered by @{buyer.display_name}", icon_url=buyer.avatar_url_as(format=None, static_format='png', size=256))
        offer_embed.set_thumbnail(url=buyer_pokemon.img_url)
        accept_emoji = self.bot.config.get('trade_accept', '\u2705')
        reject_emoji = self.bot.config.get('trade_reject', '\u274e')
        offermsg = await lister.send(f"Meowth! {buyer.display_name} offers to trade their {str(pkmn)} for your {str(listing_pokemon)}! React with {accept_emoji} to accept the offer or {reject_emoji} to reject it!", embed=offer_embed)
        self.bot.guild_dict[guild.id]['trade_dict'][listing_id]['offers'][buyer_id] = {
            "offer":str(buyer_pokemon),
            "lister_msg": offermsg.id
        }
        await utils.safe_reaction(offermsg, self.bot.config.get('trade_accept', '\u2705'))
        await utils.safe_reaction(offermsg, self.bot.config.get('trade_reject', '\u274e'))

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
            offered_pokemon = pkmn_class.Pokemon.get_pokemon(self.bot, trade_dict['offered_pokemon'])
            wanted_pokemon = pkmn_class.Pokemon.get_pokemon(self.bot, trade_dict['offers'][buyer_id]['offer'])
            complete_emoji = self.bot.config.get('trade_complete', '\u2611')
            cancel_emoji = self.bot.config.get('trade_stop', '\u23f9')
            acceptedmsg = f"Meowth! {lister.display_name} has agreed to trade their {offered_pokemon} for {buyer.display_name}'s {wanted_pokemon}. React with {complete_emoji} when the trade has been completed! To reject or cancel this offer, react with {cancel_emoji}"
            special_check = [offered_pokemon.shiny, offered_pokemon.legendary, wanted_pokemon.shiny, wanted_pokemon.legendary]
            if any(special_check):
                acceptedmsg += "\n\nThis is a Special Trade! These can only be completed once per day and can cost up to 1 million stardust! Significant discounts can be earned by leveling up your friendship before the trade is made!"
            tradermsg = await buyer.send(acceptedmsg)
            listermsg = await lister.send(acceptedmsg)
            self.bot.guild_dict[guild.id]['trade_dict'][listing_id]['status'] = "accepted"
            self.bot.guild_dict[guild.id]['trade_dict'][listing_id]['accepted'] = {"buyer_id":buyer_id, "lister_msg":listermsg.id, "buyer_msg":tradermsg.id, "lister_confirm":False, "buyer_confirm":False}
            await utils.safe_reaction(tradermsg, self.bot.config.get('trade_complete', '\u2611'))
            await utils.safe_reaction(tradermsg, self.bot.config.get('trade_stop', '\u23f9'))
            await utils.safe_reaction(listermsg, self.bot.config.get('trade_complete', '\u2611'))
            await utils.safe_reaction(listermsg, self.bot.config.get('trade_stop', '\u23f9'))
            for offerid in trade_dict['offers'].keys():
                if offerid != buyer_id:
                    reject = self.guild.get_member(offerid)
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
        offered_pokemon = pkmn_class.Pokemon.get_pokemon(self.bot, trade_dict['offered_pokemon'])
        wanted_pokemon = [pkmn_class.Pokemon.get_pokemon(self.bot, want) for want in trade_dict['wanted_pokemon'].split('\n')]
        await buyer.send(f"Meowth... {lister.display_name} rejected your offer for their {offered_pokemon}.")
        cancel_emoji = self.bot.config.get('trade_stop', '\u23f9')
        offer_str = f"Meowth! {lister.display_name} offers a {str(offered_pokemon)} up for trade!"
        instructions = "React to this message to make an offer!"
        cancel_inst = f"{lister.display_name} may cancel the trade with {cancel_emoji}"
=======

        emoji_check = [
            '\u20e3' in emoji, # keycap 1-9
            emoji == self.bot.config.get('trade_stop', '\u23f9') # stop button
        ]

        if not any(emoji_check):
            return

        if payload.user_id != self.lister_id and payload.user_id != self.bot.user.id and '\u20e3' in emoji:
            wanted_pokemon = await self.wanted_pokemon()
            i = int(emoji[0])
            offer = wanted_pokemon[i-1]
            await self.make_offer(payload.user_id, offer)

        elif payload.user_id == self.lister_id and emoji == self.bot.config.get('trade_stop', '\u23f9'):
            await self.cancel_trade()

    @property
    def guild(self):
        return self.bot.get_guild(self.guild_id)

    @property
    def listing_channel(self):
        return self.guild.get_channel(self.report_channel_id)

    @property
    def lister(self):
        return self.guild.get_member(self.lister_id)

    @staticmethod
    def make_trade_embed(lister, wanted_pokemon, offered_pokemon):
        """Returns a formatted embed message with trade details."""

        if "open trade" not in wanted_pokemon:
            wants = [
                f'{i+1}\u20e3: {pkmn}' for i, pkmn in enumerate(wanted_pokemon)
            ]
            wants = '\n'.join(wants)
        else:
            wants = "Open Trade (DM User)"

        return utils.make_embed(
            title="Pokemon Trade - {}".format(lister.display_name),
            msg_colour=utils.colour(lister.guild),
            icon=Trade.icon_url,
            fields={
                "Wants":wants,
                "Offers": str(offered_pokemon)
                },
            inline=True,
            footer=lister.display_name,
            footer_icon=lister.avatar_url_as(format='png', size=256),
            thumbnail=offered_pokemon.img_url
        )

    @staticmethod
    def make_offer_embed(trader, listed_pokemon, offer):
        return utils.make_embed(
            title="Pokemon Trade Offer - {}".format(trader.display_name),
            msg_colour=utils.colour(trader.guild),
            icon=Trade.icon_url,
            fields={
                "You Offered": str(listed_pokemon),
                "They Offer": str(offer)
                },
            inline=True,
            footer=trader.display_name,
            footer_icon=trader.avatar_url_as(format='png', size=256),
            thumbnail=offer.img_url
        )

    @classmethod
    async def create_trade(cls, ctx, wanted_pokemon, offered_pokemon):
        """Creates a trade object and sends trade details in channel"""

        trade_embed = cls.make_trade_embed(
            ctx.author, wanted_pokemon, offered_pokemon)

        role = offered_pokemon.role(ctx.guild)
        rolestr = ""

        offer_str = ("{role}Meowth! {lister} offers a {pkmn} up for trade!"
                     "").format(role=rolestr, lister=ctx.author.display_name,
                                pkmn=offered_pokemon)

        if "open trade" not in wanted_pokemon:
            instructions = "React to this message to make an offer!"
        else:
            instructions = f"DM {ctx.author.display_name} to make an offer!"

>>>>>>> parent of 28e4680b... Complete rewrite of trade. See description.
        codemsg = ""
        if ctx.author.id in ctx.bot.guild_dict[ctx.guild.id].get('trainers', {}):
            trainercode = ctx.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id].get('trainercode', None)
            if trainercode:
                codemsg += _("{user}\'s trainer code is: **{code}**").format(user=ctx.author.display_name, code=trainercode)

        cancel_inst = ("{lister} may cancel the trade with :stop_button:"
                       "").format(lister=ctx.author.display_name)

        trade_msg = await ctx.send(
            f"{offer_str}\n\n{instructions}\n\n{cancel_inst}\n\n{codemsg}",
            embed=trade_embed)

        if "open trade" not in wanted_pokemon:
            for i in range(len(wanted_pokemon)):
                await utils.safe_reaction(trade_msg, f'{i+1}\u20e3')
        await utils.safe_reaction(trade_msg, ctx.bot.config.get('trade_stop', '\u23f9'))

        trade = cls(
            ctx.bot, ctx.author.id, trade_msg.id, ctx.channel.id, ctx.guild.id,
            wanted_pokemon, offered_pokemon
        )

        ctx.bot.add_listener(trade.on_raw_reaction_add)

        return trade

    @classmethod
    def from_data(cls, bot, message_id, data):
        trade = cls(
            bot, data['lister_id'], message_id, data['report_channel_id'],
            data['guild_id'], data['wanted_pokemon'], data['offered_pokemon']
        )

        bot.add_listener(trade.on_raw_reaction_add)

        return trade

    async def get_listmsg(self):
        return await self.listing_channel.fetch_message(self.listing_id)

    async def offered_pokemon(self):
        listingmsg = await self.get_listmsg()
        ctx = await self.bot.get_context(listingmsg)
        return pkmn_class.Pokemon.get_pokemon(ctx.bot, self._data['offered_pokemon'])

    async def wanted_pokemon(self):
        listingmsg = await self.get_listmsg()
        ctx = await self.bot.get_context(listingmsg)
        return [pkmn_class.Pokemon.get_pokemon(ctx.bot, want) for want in self._data['wanted_pokemon']]

    async def make_offer(self, trader_id, pkmn):
        offered_pokemon = await self.offered_pokemon()
        self.offers[trader_id] = str(pkmn)
        trader = self.guild.get_member(trader_id)
        offer_embed = self.make_offer_embed(trader, offered_pokemon, pkmn)

        offermsg = await self.lister.send(
            ("Meowth! {trader} offers to trade their {pkmn} for your {offer}! "
             "React with {accept_emoji} to accept the offer or "
             "{reject_emoji} to reject it!").format(
                 trader=trader.display_name, pkmn=pkmn, offer=offered_pokemon, accept_emoji=self.bot.config.get('trade_accept', '\u2705'), reject_emoji=self.bot.config.get('trade_reject', '\u274e')),
            embed=offer_embed)

        reaction, __ = await utils.ask(self.bot, offermsg, timeout=None)

        if reaction.emoji == self.bot.config.get('trade_accept', '\u2705'):
            await self.accept_offer(trader_id)
            await utils.safe_delete(offermsg)

        elif reaction.emoji == self.bot.config.get('trade_reject', '\u274e'):
            await self.reject_offer(trader_id)
            await utils.safe_delete(offermsg)

    async def accept_offer(self, offer_id):
        offer = self.offers[offer_id]
        trader = self.guild.get_member(offer_id)
        lister = self.lister
        listingmsg = await self.get_listmsg()

        ctx = await self.bot.get_context(listingmsg)
        offer = pkmn_class.Pokemon.get_pokemon(ctx.bot, offer)
        offered_pokemon = await self.offered_pokemon()

        acceptedmsg = (
            "Meowth! {} has agreed to trade their {} for {}'s {}\n\n"
            "Please DM them to coordinate the trade! "
            "React with {} when the trade has been "
            "completed! To reject or cancel this offer, react with "
            "{}").format(
                self.lister.display_name,
                offered_pokemon,
                trader.display_name,
                offer, self.bot.config.get('trade_complete', '\u2611'), self.bot.config.get('trade_stop', '\u23f9'))

        special_check = [
            offered_pokemon.shiny,
            offered_pokemon.legendary,
            offer.shiny,
            offer.legendary
        ]

        if any(special_check):
            acceptedmsg += (
                "\n\nThis is a Special Trade! These can only be "
                "completed once per day and can cost up to 1 million "
                "stardust! Significant discounts can be earned by leveling "
                "up your friendship before the trade is made!")

        tradermsg = await trader.send(acceptedmsg)
        listermsg = await lister.send(acceptedmsg)

        await utils.safe_reaction(tradermsg, self.bot.config.get('trade_complete', '\u2611'))
        await utils.safe_reaction(tradermsg, self.bot.config.get('trade_stop', '\u23f9'))
        await utils.safe_reaction(listermsg, self.bot.config.get('trade_complete', '\u2611'))
        await utils.safe_reaction(listermsg, self.bot.config.get('trade_stop', '\u23f9'))

        for offerid in self.offers.keys():
            if offerid != offer_id:
                reject = self.guild.get_member(offerid)
                try:
                    await reject.send((
                        "Meowth... {} accepted a competing offer for their {}."
                        "").format(self.lister.display_name, offered_pokemon))
                except discord.HTTPException:
                    pass



        await listingmsg.edit(
            content="Meowth! {} has accepted an offer!".format(
                self.lister.display_name),
            )

        await listingmsg.clear_reactions()

        trader_confirms = False
        lister_confirms = False

        def check(r, u):
            user_check = [u == trader, u == lister]
            msg_check = [r.message.id == tradermsg.id, r.message.id == listermsg.id]
            emoji_check = [r.emoji == self.bot.config.get('trade_complete', '\u2611'), r.emoji == self.bot.config.get('trade_stop', '\u23f9')]
            if not any(msg_check) or not any(user_check) or not any(emoji_check):
                return False
            else:
                return True

        while True:
            reaction, user = await self.bot.wait_for('reaction_add', check=check)
            if user.id == trader.id:
                if reaction.emoji == self.bot.config.get('trade_complete', '\u2611'):
                    trader_confirms = True
                elif reaction.emoji == self.bot.config.get('trade_stop', '\u23f9'):
                    await utils.safe_delete(tradermsg)
                    return await self.withdraw_offer(trader.id)
            elif user.id == lister.id:
                if reaction.emoji == self.bot.config.get('trade_complete', '\u2611'):
                    lister_confirms = True
                elif reaction.emoji == self.bot.config.get('trade_stop', '\u23f9'):
                    await utils.safe_delete(listermsg)
                    return await self.reject_offer(trader.id)
            if trader_confirms and lister_confirms:
                await utils.safe_delete(listermsg)
                await utils.safe_delete(tradermsg)
                return await self.confirm_trade()
            else:
                continue

        # update the listing message if it still exists
        # dm others who offered saying the trade was completed
        # dm the member with the successful offer with details for trade
        # maybe ask the lister to provide a friend code optionally before dm

    async def withdraw_offer(self, offer_id):
        offered_pokemon = await self.offered_pokemon()
        wanted_pokemon = await self.wanted_pokemon()
        listingmsg = await self.get_listmsg()
        trader = self.guild.get_member(offer_id)
        await self.lister.send(
            "Meowth... {} withdrew their trade offer of {}.".format(
                trader.display_name, self.offers[offer_id]))

        offer_str = "Meowth! {lister} offers a {pkmn} up for trade!".format(
            lister=self.lister.display_name, pkmn=offered_pokemon)

        instructions = "React to this message to make an offer!"
        cancel_inst = "{lister} may cancel the trade with {stop_emoji}".format(
            lister=self.lister.display_name, stop_emoji=self.bot.config.get('trade_stop', '\u23f9'))

        await listingmsg.edit(
            content=f"{offer_str}\n\n{instructions}\n\n{cancel_inst}",
            )

        for i in range(len(wanted_pokemon)):
            await utils.safe_reaction(listingmsg, f'{i+1}\u20e3')

        await utils.safe_reaction(listingmsg, self.bot.config.get('trade_stop', '\u23f9'))
        del self.offers[offer_id]

    async def reject_offer(self, offer_id):
        listingmsg = await self.get_listmsg()
        trader = self.guild.get_member(offer_id)
        offered_pokemon = await self.offered_pokemon()
        wanted_pokemon = await self.wanted_pokemon()

        await trader.send(
            "Meowth... {} rejected your offer for their {}.".format(
                self.lister.display_name, offered_pokemon))

        offer_str = "Meowth! {lister} offers a {pkmn} up for trade!".format(
            lister=self.lister.display_name, pkmn=offered_pokemon)

        instructions = "React to this message to make an offer!"
        cancel_inst = "{lister} may cancel the trade with {stop_emoji}".format(
            lister=self.lister.display_name, stop_emoji=self.bot.config.get('trade_stop', '\u23f9'))

        await listingmsg.edit(
            content=f"{offer_str}\n\n{instructions}\n\n{cancel_inst}",
            )

        for i in range(len(wanted_pokemon)):
            await utils.safe_reaction(listingmsg, f'{i+1}\u20e3')

        await utils.safe_reaction(listingmsg, self.bot.config.get('trade_stop', '\u23f9'))

        del self.offers[offer_id]

    async def cancel_trade(self):
        offered_pokemon = await self.offered_pokemon()
        for offerid in self.offers:
            reject = self.guild.get_member(offerid)

            await reject.send(
                "Meowth... {} canceled their trade offer of {}".format(
                    self.lister.display_name, offered_pokemon))

        await self.close_trade()

        # update the listing message if it still exists
        # dm those who offered saying the trade was cancelled

    async def confirm_trade(self):
        listingmsg = await self.get_listmsg()
        await listingmsg.edit(content='Meowth! This trade has been completed!', embed=None)
        await asyncio.sleep(5)
        await self.close_trade()

    async def close_trade(self):
        listingmsg = await self.get_listmsg()
        await utils.safe_delete(listingmsg)
        self.bot.remove_listener(self.on_raw_reaction_add)
        try:
            guild_trades = self.bot.guild_dict[self.guild_id]['trade_dict']
            del guild_trades[self.report_channel_id][self.listing_id]
            await utils.safe_delete(listingmsg)
        except (KeyError, discord.HTTPException):
            pass

class Trading(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        for guild_id in self.bot.guild_dict:
            trade_dict = self.bot.guild_dict[guild_id].setdefault('trade_dict', {})
            for channel_id in trade_dict:
                trade_channel_data = trade_dict[channel_id]
                for message_id in trade_channel_data:
                    Trade.from_data(
                        self.bot, message_id, trade_channel_data[message_id])

    # async def on_message(self, message):
    #     ctx = await self.bot.get_context(message)
    #     if not ctx.guild:
    #         return
    #     if checks.check_tradereport(ctx) and message.author != ctx.guild.me:
    #         await asyncio.sleep(1)
    #         await utils.safe_delete(message)

    @commands.command()
    @checks.allowtrade()
<<<<<<< HEAD
    async def trade(self, ctx, *, offered_pokemon: pkmn_class.Pokemon=None):
=======
    async def trade(self, ctx, *, offer: pkmn_class.Pokemon):
>>>>>>> parent of 28e4680b... Complete rewrite of trade. See description.
        """Create a trade listing."""
        await utils.safe_delete(ctx.message)
        await ctx.trigger_typing()
        if type(offer) == dict:
            trade_error = await ctx.send(
                f"{ctx.author.display_name}, check your spelling and make sure "
                f"you are only listing one pokemon.", delete_after=5)
            return

        preview_embed = discord.Embed(colour=utils.colour(ctx.guild))
        preview_embed.set_thumbnail(url=offer.img_url)

        want_ask = await ctx.send(
            f"{ctx.author.mention}, what Pokemon are you willing to accept "
            f"in exchange for {str(offer)}?\n\nList your pokemon in a comma "
            f"separated list, reply with **ask** to create an open trade, or "
            f"reply with **cancel** to cancel", embed=preview_embed)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            want_reply = await ctx.bot.wait_for('message', check=check, timeout=60)
        except asyncio.TimeoutError:
            await utils.safe_delete(want_ask)
            return

        wants = want_reply.content.lower().split(',')

        if len(wants) > 9:
            trade_error = await ctx.send(
                f"{ctx.author.display_name}, please limit your trade to 9 or "
                f"fewer pokemon. Try again!", delete_after=5)
            return

        await utils.safe_delete(want_ask)
        await utils.safe_delete(want_reply)

        if "ask" in wants:
            wants = "open trade"
        elif wants[0].lower() == "cancel":
            return
        else:
            wants = [x.strip() for x in wants]
            wants = [pkmn_class.Pokemon.get_pokemon(ctx.bot, x) for x in wants]
            wants = [x for x in wants if x]
            wants = [str(want) for want in wants]
        if not wants:
            trade_error = await ctx.send(
                f"{ctx.author.display_name}, please check your input. Try again!", delete_after=5)
            return

        await Trade.create_trade(ctx, wants, offer)


def setup(bot):
    bot.add_cog(Trading(bot))
