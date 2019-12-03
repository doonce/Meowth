import asyncio
import functools
import datetime
import time
import logging
import copy
import traceback

import discord
from discord.ext import commands, tasks

from meowth import checks

from meowth.exts import pokemon as pkmn_class
from meowth.exts import utilities as utils

logger = logging.getLogger("meowth")

class Trading(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.emoji_dict = {0: u'\U00000030\U0000fe0f\U000020e3', 1: u'\U00000031\U0000fe0f\U000020e3', 2: u'\U00000032\U0000fe0f\U000020e3', 3: u'\U00000033\U0000fe0f\U000020e3', 4: u'\U00000034\U0000fe0f\U000020e3', 5: u'\U00000035\U0000fe0f\U000020e3', 6: u'\U00000036\U0000fe0f\U000020e3', 7: u'\U00000037\U0000fe0f\U000020e3', 8: u'\U00000038\U0000fe0f\U000020e3', 9: u'\U00000039\U0000fe0f\U000020e3', 10: u'\U0001f51f'}
        self.trade_cleanup.start()

    def cog_unload(self):
        self.trade_cleanup.cancel()

    @tasks.loop(seconds=86400)
    async def trade_cleanup(self, loop=True):
        logger.info('------ BEGIN ------')
        yes_emoji = self.bot.custom_emoji.get('trade_complete', u'\U00002611\U0000fe0f')
        no_emoji = self.bot.custom_emoji.get('trade_stop', u'\U000023f9\U0000fe0f')
        for guild in list(self.bot.guilds):
            try:
                trade_dict = self.bot.guild_dict[guild.id].setdefault('trade_dict', {})
                for listing_id in list(trade_dict.keys()):
                    if trade_dict.get(listing_id, {}).get('exp', 0) <= time.time():
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
                                if not lister:
                                    await self.close_trade(guild.id, listing_id)
                                    continue
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
            except Exception as e:
                print(traceback.format_exc())
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
        guild = getattr(channel, "guild", None)
        try:
            user = self.bot.get_user(payload.user_id)
        except AttributeError:
            return
        if user.bot or user == self.bot.user:
            return
        if guild:
            user = guild.get_member(payload.user_id)
        elif not guild and not channel:
            channel = user.dm_channel
            if not channel:
                channel = await user.create_dm()
            if not channel:
                return
        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.errors.NotFound, AttributeError, discord.Forbidden):
            return
        ctx = await self.bot.get_context(message)
        emoji = payload.emoji.name
        active_check_dict = {}
        offer_dict = {}
        accepted_dict = {}
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
                if user.id != trade_dict[message.id]['lister_id'] and (u'\U000020e3' in emoji or u'\U0001f51f' in emoji):
                    wanted_pokemon = trade_dict[message.id]['wanted_pokemon']
                    wanted_pokemon = wanted_pokemon.encode('ascii', 'ignore').decode("utf-8").replace(":", "")
                    wanted_pokemon = [await pkmn_class.Pokemon.async_get_pokemon(self.bot, want) for want in wanted_pokemon.split("\n")]
                    i = int(emoji[0])
                    offer = wanted_pokemon[i-1]
                    await self.make_offer(message.guild.id, message.id, user.id, offer)
                elif payload.user_id == trade_dict[message.id]['lister_id'] and emoji == self.bot.custom_emoji.get('trade_stop', u'\U000023f9\U0000fe0f'):
                    await self.cancel_trade(message.guild.id, message.id)
                elif payload.user_id == trade_dict[message.id]['lister_id'] and emoji == self.bot.custom_emoji.get('trade_info', u'\U00002139\U0000fe0f'):
                    await message.remove_reaction(self.bot.custom_emoji.get('trade_info', u'\U00002139\U0000fe0f'), user)
                    await self.add_trade_details(ctx, message)
                elif str(payload.emoji) == self.bot.custom_emoji.get('trade_report', u'\U0001F4E2'):
                    ctx = await self.bot.get_context(message)
                    ctx.author, ctx.message.author = user, user
                    await message.remove_reaction(payload.emoji, user)
                    return await ctx.invoke(self.bot.get_command('trade'))
                elif str(payload.emoji) == self.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f'):
                    await asyncio.sleep(0.25)
                    await message.remove_reaction(payload.emoji, self.bot.user)
                    await asyncio.sleep(0.25)
                    await message.remove_reaction(payload.emoji, user)
                    await ctx.invoke(self.bot.get_command("list trades"), search="all")
                    await asyncio.sleep(5)
                    await utils.safe_reaction(message, payload.emoji)
                elif str(payload.emoji) == self.bot.custom_emoji.get('trade_search', u'\U0001f50d'):
                    await message.remove_reaction(payload.emoji, user)
                    await ctx.invoke(self.bot.get_command("list searching"), search="all")
        elif message.id in active_check_dict.keys():
            guild = self.bot.get_guild(active_check_dict[message.id]['guild_id'])
            listing_id = active_check_dict[message.id]['listing_id']
            trade_dict = self.bot.guild_dict[guild.id]['trade_dict'][listing_id]
            if emoji == self.bot.custom_emoji.get('trade_complete', u'\U00002611\U0000fe0f'):
                self.bot.guild_dict[guild.id]['trade_dict'][listing_id]['exp'] = time.time() + 30*24*60*60
                self.bot.guild_dict[guild.id]['trade_dict'][listing_id]['active_check'] = None
            elif emoji == self.bot.custom_emoji.get('trade_stop', u'\U000023f9\U0000fe0f'):
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
            if emoji == self.bot.custom_emoji.get('trade_accept', u'\U00002705'):
                await self.accept_offer(guild.id, offer_dict[message.id]['listing_id'], offer_dict[message.id]['buyer_id'])
            elif emoji == self.bot.custom_emoji.get('trade_reject', u'\U0000274e'):
                await self.reject_offer(guild.id, offer_dict[message.id]['listing_id'], offer_dict[message.id]['buyer_id'])
            await message.delete()
        elif message.id in accepted_dict.keys():
            guild = self.bot.get_guild(accepted_dict[message.id]['guild_id'])
            trade_dict = self.bot.guild_dict[guild.id]['trade_dict'][accepted_dict[message.id]['listing_id']]
            if emoji == self.bot.custom_emoji.get('trade_complete', u'\U00002611\U0000fe0f'):
                await self.confirm_trade(guild.id, accepted_dict[message.id]['listing_id'], user.id)
            elif emoji == self.bot.custom_emoji.get('trade_stop', u'\U000023f9\U0000fe0f'):
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
        if not lister:
            return await self.close_trade(guild_id, listing_id)
        offer_embed = discord.Embed(colour=guild.me.colour)
        offer_embed.set_author(name="Pokemon Trade Offer - {}".format(buyer.display_name), icon_url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/trade_icon_small.png")
        offer_embed.add_field(name="You Offered", value=str(listing_pokemon), inline=True)
        offer_embed.add_field(name="They Offer", value=str(buyer_pokemon), inline=True)
        offer_embed.set_footer(text=f"Offered by @{buyer.display_name}", icon_url=buyer.avatar_url_as(format=None, static_format='png', size=256))
        offer_embed.set_thumbnail(url=buyer_pokemon.img_url)
        accept_emoji = self.bot.custom_emoji.get('trade_accept', u'\U00002705')
        reject_emoji = self.bot.custom_emoji.get('trade_reject', u'\U0000274e')
        offermsg = await lister.send(f"Meowth! {buyer.display_name} offers to trade their {str(pkmn)} for your {str(listing_pokemon)}! React with {accept_emoji} to accept the offer or {reject_emoji} to reject it!", embed=offer_embed)
        self.bot.guild_dict[guild.id]['trade_dict'][listing_id]['offers'][buyer_id] = {
            "offer":str(buyer_pokemon),
            "lister_msg": offermsg.id
        }
        await utils.safe_reaction(offermsg, self.bot.custom_emoji.get('trade_accept', u'\U00002705'))
        await utils.safe_reaction(offermsg, self.bot.custom_emoji.get('trade_reject', u'\U0000274e'))

    async def accept_offer(self, guild_id, listing_id, buyer_id):
        guild = self.bot.get_guild(guild_id)
        trade_dict = self.bot.guild_dict[guild.id]['trade_dict'][listing_id]
        if trade_dict['status'] == "active":
            buyer = guild.get_member(buyer_id)
            if not buyer:
                return
            lister = guild.get_member(trade_dict['lister_id'])
            channel = self.bot.get_channel(trade_dict['report_channel_id'])
            try:
                listing_msg = await channel.fetch_message(listing_id)
            except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                await self.close_trade(guild_id, listing_id)
            if not lister:
                return await self.close_trade(guild.id, listing_id)
            offered_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, trade_dict['offered_pokemon'])
            wanted_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, trade_dict['offers'][buyer_id]['offer'])
            complete_emoji = self.bot.custom_emoji.get('trade_complete', u'\U00002611\U0000fe0f')
            cancel_emoji = self.bot.custom_emoji.get('trade_stop', u'\U000023f9\U0000fe0f')
            acceptedmsg = f"Meowth! {lister.display_name} has agreed to trade their {offered_pokemon} for {buyer.display_name}'s {wanted_pokemon}. React with {complete_emoji} when the trade has been completed! To reject or cancel this offer, react with {cancel_emoji}"
            special_check = [offered_pokemon.shiny, offered_pokemon.legendary, wanted_pokemon.shiny, wanted_pokemon.legendary, wanted_pokemon.shadow == "purified"]
            if any(special_check):
                acceptedmsg += "\n\nThis is a Special Trade! These can only be completed once per day and can cost up to 1 million stardust! Significant discounts can be earned by leveling up your friendship before the trade is made!"
            tradermsg = await buyer.send(acceptedmsg)
            listermsg = await lister.send(acceptedmsg)
            self.bot.guild_dict[guild.id]['trade_dict'][listing_id]['status'] = "accepted"
            self.bot.guild_dict[guild.id]['trade_dict'][listing_id]['accepted'] = {"buyer_id":buyer_id, "lister_msg":listermsg.id, "buyer_msg":tradermsg.id, "lister_confirm":False, "buyer_confirm":False}
            await utils.safe_reaction(tradermsg, self.bot.custom_emoji.get('trade_complete', u'\U00002611\U0000fe0f'))
            await utils.safe_reaction(tradermsg, self.bot.custom_emoji.get('trade_stop', u'\U000023f9\U0000fe0f'))
            await utils.safe_reaction(listermsg, self.bot.custom_emoji.get('trade_complete', u'\U00002611\U0000fe0f'))
            await utils.safe_reaction(listermsg, self.bot.custom_emoji.get('trade_stop', u'\U000023f9\U0000fe0f'))
            for offerid in trade_dict['offers'].keys():
                if offerid != buyer_id:
                    reject = guild.get_member(offerid)
                    if not reject:
                        continue
                    try:
                        await reject.send(f"Meowth... {lister.display_name} accepted a competing offer for their {offered_pokemon}.")
                    except discord.HTTPException:
                        pass
            await listing_msg.edit(content=f"Meowth! {lister.display_name} has accepted an offer!")
            await listing_msg.clear_reactions()

    async def reject_offer(self, guild_id, listing_id, buyer_id):
        guild = self.bot.get_guild(guild_id)
        trade_dict = self.bot.guild_dict[guild.id]['trade_dict'][listing_id]
        if not buyer:
            return
        lister = guild.get_member(trade_dict['lister_id'])
        channel = self.bot.get_channel(trade_dict['report_channel_id'])
        info_emoji = ctx.bot.custom_emoji.get('trade_info', u'\U00002139\U0000fe0f')
        report_emoji = ctx.bot.custom_emoji.get('trade', u'\U0001F4E2')
        search_emoji = ctx.bot.custom_emoji.get('trade_search', u'\U0001f50d')
        list_emoji = ctx.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f')
        try:
            listing_msg = await channel.fetch_message(listing_id)
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
            await self.close_trade(guild_id, listing_id)
        if not lister:
            return await self.close_trade(guild.id, listing_id)
        offered_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, trade_dict['offered_pokemon'])
        wanted_pokemon = trade_dict['wanted_pokemon']
        wanted_pokemon = wanted_pokemon.encode('ascii', 'ignore').decode("utf-8").replace(":", "")
        wanted_pokemon = [await pkmn_class.Pokemon.async_get_pokemon(self.bot, want) for want in wanted_pokemon.split("\n")]
        try:
            await buyer.send(f"Meowth... {lister.display_name} rejected your offer for their {offered_pokemon}.")
        except:
            pass
        cancel_emoji = self.bot.custom_emoji.get('trade_stop', u'\U000023f9\U0000fe0f')
        if lister.id in self.bot.guild_dict[guild.id].get('trainers', {}):
            trainercode = self.bot.guild_dict[guild.id]['trainers'][lister.id].get('trainercode', None)
        offered_pokemon_str = f"Meowth! {lister.mention} {'(trainercode: **'+trainercode+'**) ' if trainercode else ''}offers a {str(offered_pokemon)} up for trade!"
        if "open trade" not in wanted_pokemon.lower():
            instructions = "React to this message to make an offer!"
        else:
            instructions = f"DM {lister.display_name} to make an offer!"
        instructions += f"\n\n{lister.display_name} can use {trade_stop} to cancel or {info_emoji} to edit details. Everyone can use {report_emoji} to report new, {search_emoji} to list desired pokemon, or {list_emoji} to list all active trades!"
        await listing_msg.edit(content=f"{offered_pokemon_str} {instructions}")
        for i in range(len(wanted_pokemon)):
            await utils.safe_reaction(listing_msg, f'{self.emoji_dict[i+1]}')
        await utils.safe_reaction(listing_msg, self.bot.custom_emoji.get('trade_stop', u'\U000023f9\U0000fe0f'))
        del trade_dict['offers'][buyer_id]
        self.bot.guild_dict[guild.id]['trade_dict'][listing_id]['status'] = "active"

    async def withdraw_offer(self, guild_id, listing_id, buyer_id):
        guild = self.bot.get_guild(guild_id)
        trade_dict = self.bot.guild_dict[guild.id]['trade_dict'][listing_id]
        buyer = guild.get_member(buyer_id)
        lister = guild.get_member(trade_dict['lister_id'])
        channel = self.bot.get_channel(trade_dict['report_channel_id'])
        info_emoji = ctx.bot.custom_emoji.get('trade_info', u'\U00002139\U0000fe0f')
        report_emoji = ctx.bot.custom_emoji.get('trade_report', u'\U0001F4E2')
        search_emoji = ctx.bot.custom_emoji.get('trade_search', u'\U0001f50d')
        list_emoji = ctx.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f')
        try:
            listing_msg = await channel.fetch_message(listing_id)
        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
            await self.close_trade(guild_id, listing_id)
        if not lister:
            return await self.close_trade(guild.id, listing_id)
        offered_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, trade_dict['offered_pokemon'])
        wanted_pokemon = trade_dict['wanted_pokemon']
        wanted_pokemon = wanted_pokemon.encode('ascii', 'ignore').decode("utf-8").replace(":", "")
        wanted_pokemon = [await pkmn_class.Pokemon.async_get_pokemon(self.bot, want) for want in wanted_pokemon.split("\n")]
        buyer_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, trade_dict['offers'][buyer_id]['offer'])
        cancel_emoji = self.bot.custom_emoji.get('trade_stop', u'\U000023f9\U0000fe0f')
        await lister.send(f"Meowth... {buyer.display_name} withdrew their trade offer of {str(buyer_pokemon)}.")
        if lister.id in self.bot.guild_dict[guild.id].get('trainers', {}):
            trainercode = self.bot.guild_dict[guild.id]['trainers'][lister.id].get('trainercode', None)
        offered_pokemon_str = f"Meowth! {lister.mention} {'(trainercode: **'+trainercode+'**) ' if trainercode else ''}offers a {str(offered_pokemon)} up for trade!"
        if "open trade" not in wanted_pokemon.lower():
            instructions = "React to this message to make an offer!"
        else:
            instructions = f"DM {lister.display_name} to make an offer!"
        instructions += f"\n\n{lister.display_name} can use {trade_stop} to cancel or {info_emoji} to edit details. Everyone can use {report_emoji} to report new, {search_emoji} to list desired pokemon, or {list_emoji} to list all active trades!"
        await listing_msg.edit(content=f"{offered_pokemon_str} {instructions}")
        for i in range(len(wanted_pokemon)):
            await utils.safe_reaction(listing_msg, f'{self.emoji_dict[i+1]}')
        await utils.safe_reaction(listing_msg, self.bot.custom_emoji.get('trade_stop', u'\U000023f9\U0000fe0f'))
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
            if not reject:
                continue
            await reject.send(f"Meowth... {lister.display_name} canceled their trade offer of {str(offered_pokemon)}")
            await utils.expire_dm_reports(self.bot, {lister.id: trade_dict['offers'][offerid]['lister_msg']})
        await self.close_trade(guild_id, listing_id)

    async def add_trade_details(self, ctx, message):
        message = ctx.message
        channel = message.channel
        guild = message.guild
        trade_dict = self.bot.guild_dict[guild.id]['trade_dict'][message.id]
        lister = guild.get_member(trade_dict['lister_id'])
        ctx.author = lister
        channel = self.bot.get_channel(trade_dict['report_channel_id'])
        wanted_pokemon = trade_dict['wanted_pokemon']
        wanted_pokemon = wanted_pokemon.encode('ascii', 'ignore').decode("utf-8").replace(":", "")
        wanted_pokemon = [await pkmn_class.Pokemon.async_get_pokemon(self.bot, want) for want in wanted_pokemon.split('\n')]
        wanted_pokemon = [str(x) for x in wanted_pokemon if x]
        offered_pokemon = trade_dict['offered_pokemon']
        trade_details = str(trade_dict.get('details', ""))
        trade_offers = trade_dict.get('offers', {})
        info_emoji = ctx.bot.custom_emoji.get('trade_info', u'\U00002139\U0000fe0f')
        if not lister:
            return
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[channel.guild.id]['configure_dict']['settings']['offset']))
        error = False
        success = []
        reply_msg = f"**wanted <want list>** - Current: {(', ').join(wanted_pokemon)}\n"
        reply_msg += f"**details <details>** - Current: {trade_details}\n"
        reply_msg += f"**offer <offered pokemon>** - Current: {offered_pokemon}\n"
        trade_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/pogo_trading_icon.png?cache=1')
        trade_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=lister.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=lister.avatar_url_as(format=None, static_format='jpg', size=32))
        while True:
            async with ctx.typing():
                trade_embed.add_field(name=_('**Edit Trade Info**'), value=f"Meowth! I'll help you add information to your {offered_pokemon} trade! I'll need to know what **values** you'd like to edit. Reply **cancel** to stop anytime or reply with one of the following options `Ex: wanted shiny caterpie, shiny charizard` or `details My offer has a legacy moveset, I'm looking for a great league trade. Trade is negotiable.`:\n\n{reply_msg}\n**NOTE**: Editing will cancel your old trade along with all active offers.", inline=False)
                value_wait = await channel.send(embed=trade_embed)
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
                    if value_msg.clean_content.lower().startswith('wanted'):
                        if value_msg.clean_content.lower().split()[1] == "ask" or value_msg.clean_content.lower().split()[1] == "open":
                            wanted_pokemon = "open trade"
                        else:
                            wanted_pokemon = value_msg.clean_content.lower().split(',')
                            wanted_pokemon = [x.strip() for x in wanted_pokemon]
                            wanted_pokemon = [await pkmn_class.Pokemon.async_get_pokemon(self.bot, x) for x in wanted_pokemon]
                            for pkmn in wanted_pokemon:
                                if pkmn.shadow == "shadow":
                                    pkmn.shadow = False
                            wanted_pokemon = [str(x) for x in wanted_pokemon if x]
                            if len(wanted_pokemon) > 10:
                                error = _("entered more than ten pokemon")
                                break
                        success.append("wanted")
                    elif value_msg.clean_content.lower().startswith('offer'):
                        offered_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, value_msg.clean_content.lower().replace('offer', "", 1))
                        if not offered_pokemon:
                            error = _("entered something invalid")
                            break
                        offered_pokemon = str(offered_pokemon)
                        success.append("offer")
                    elif value_msg.clean_content.lower().startswith('details'):
                        trade_details = value_msg.clean_content.lower().replace('details', "", 1)
                        success.append("details")
                    else:
                        error = _("entered something invalid")
                    break
        if error:
            trade_embed.clear_fields()
            trade_embed.add_field(name=_('**Trade Edit Cancelled**'), value=f"Meowth! Your edit has been cancelled because you **{error}**! Retry when you're ready.", inline=False)
            if success:
                trade_embed.set_field_at(0, name="**Trade Edit Error**", value=f"Meowth! Your **{(', ').join(success)}** edits were successful, but others were skipped because you **{error}**! Retry when you're ready.", inline=False)
            confirmation = await channel.send(embed=trade_embed, delete_after=10)
        else:
            await self.send_trade(ctx, wanted_pokemon, offered_pokemon, trade_details)
            await self.cancel_trade(message.guild.id, message.id)

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
            await utils.expire_dm_reports(self.bot, trade_dict.get('dm_dict', {}))
        except:
            pass
        try:
            del self.bot.guild_dict[guild_id]['trade_dict'][listing_id]
        except (KeyError, discord.HTTPException):
            pass

    @commands.command()
    @checks.allowtrade()
    async def trade(self, ctx, *, offered_pokemon=''):
        """Create a trade listing.

        Usage: !trade [pokemon list]
        Meowth will guide you through listing pokemon for trade"""
        if not ctx.message.embeds:
            await utils.safe_delete(ctx.message)
        trade_dict = self.bot.guild_dict[ctx.guild.id].setdefault('trade_dict', {})
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[ctx.channel.guild.id]['configure_dict']['settings']['offset'])).strftime(_('%I:%M %p (%H:%M)'))
        error = False
        details = None
        all_offered = offered_pokemon.split(',')
        all_offered = [x.strip() for x in all_offered]
        info_emoji = ctx.bot.custom_emoji.get('trade_info', u'\U00002139\U0000fe0f')
        for index, item in enumerate(all_offered):
            pokemon, __ = await pkmn_class.Pokemon.ask_pokemon(ctx, item)
            all_offered[index] = pokemon
        all_offered = [x for x in all_offered if x]
        preview_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/pogo_trading_icon.png?cache=1')
        preview_embed.set_footer(text=f"Listed by @{ctx.author.display_name} - {timestamp}", icon_url=ctx.author.avatar_url_as(format=None, static_format='png', size=256))
        async def error_msg(e):
            preview_embed.clear_fields()
            preview_embed.add_field(name=_('**Trade Listing Cancelled**'), value=_("Meowth! Your listing has been cancelled because you {error}! Retry when you're ready.").format(error=e), inline=False)
            confirmation = await ctx.send(embed=preview_embed, delete_after=10)
        while True:
            async with ctx.typing():
                def check(m):
                    return m.author == ctx.author and m.channel == ctx.channel
                if not all_offered:
                    preview_embed.add_field(name=_('**New Trade Listing**'), value=f"Meowth! I'll help you list a new trade! What pokemon are you wanting to list for trade? Reply with your **pokemon** or reply with **cancel** to cancel.\n\nYour **pokemon** can contain any forms, shiny, or gender. I'll try to match it as close as possible.\n\nIf you have pokemon that you are *looking for*, enter a pokemon you would be willing to trade for them.", inline=False)
                    trade_listing = await ctx.send(embed=preview_embed)
                    try:
                        listing_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        listing_msg = None
                    await utils.safe_delete(trade_listing)
                    if not listing_msg:
                        error = _("took too long to respond")
                        await error_msg(error)
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
                            if pokemon and pokemon.shadow == "shadow":
                                pokemon.shadow = False
                            all_offered[index] = pokemon
                        all_offered = [x for x in all_offered if x]
                        if not all_offered:
                            error = _("entered something invalid")
                            await error_msg(error)
                            return
                list_separate = True
                if len(all_offered) > 1:
                    preview_embed.clear_fields()
                    preview_embed.add_field(name=f"New Trade Listing", value=f"You listed multiple pokemon for trade. Do you want different things in exchange for them or will they all be the same? Reply with **same** to set all of your {len(all_offered)} to the same pokemon in return, reply with **different** to set each of your {len(all_offered)} trades separately, or reply with **cancel** to cancel all {len(all_offered)} trades.\n\nNote: You can modify trades later with {info_emoji}.", inline=False)
                    separate_wait = await ctx.send(embed=preview_embed)
                    try:
                        separate_reply = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        separate_reply = None
                    await utils.safe_delete(separate_wait)
                    if not separate_reply:
                        error = _("took too long to respond")
                        await error_msg(error)
                        return
                    else:
                        await utils.safe_delete(separate_reply)
                    if separate_reply.clean_content.lower() == "cancel":
                        error = _("cancelled the listing")
                        await error_msg(error)
                        break
                    elif separate_reply.clean_content.lower() == "same":
                        list_separate = False
                    elif separate_reply.clean_content.lower() == "different":
                        list_separate = True
                    else:
                        error = _("entered something invalid")
                        await error_msg(error)
                        break
                first_listing = True
                for offered_pokemon in all_offered:
                    if list_separate or first_listing:
                        preview_embed.clear_fields()
                        preview_embed.set_thumbnail(url=offered_pokemon.img_url)
                        preview_embed.add_field(name=f"New Trade Listing", value=f"What pokemon are you willing to accept in exchange for your {str(offered_pokemon) if list_separate else str(len(all_offered))+' trades'}?\n\nList up to ten pokemon in a comma separated list, reply with **open** to create an open trade and invite offers, or reply with **cancel** to cancel this listing.{' Reply with **stop** to cancel all listed trades.' if len(all_offered) > 1 else ''}", inline=False)
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
                        if len(wanted_pokemon) > 10:
                            error = _("entered more than ten pokemon")
                            await error_msg(error)
                            continue
                        if "ask" in wanted_pokemon or "open" in wanted_pokemon:
                            wanted_pokemon = "open trade"
                        else:
                            wanted_pokemon_list = []
                            for pkmn in wanted_pokemon:
                                pkmn = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, pkmn)
                                if pkmn and str(pkmn) not in wanted_pokemon_list:
                                    if pkmn.shadow == "shadow":
                                        pkmn.shadow = False
                                    wanted_pokemon_list.append(str(pkmn))
                            wanted_pokemon = wanted_pokemon_list
                        if not wanted_pokemon:
                            error = _("entered something invalid")
                            await error_msg(error)
                            return
                        details = ""
                        if list_separate:
                            preview_embed.set_field_at(0, name=preview_embed.fields[0].name, value=f"Great! Now, would you like to add some **details** to your trade? This can be something like 'My offer has a legacy moveset, I'm looking for a great league trade. Trade is negotiable.'\n\nReply with your **details** to add them, reply with **none** to list without any details, or reply with **cancel** to cancel this listing.{' Reply with **stop** to cancel all listed trades.' if len(all_offered) > 1 else ''}", inline=False)
                            details_want = await ctx.send(embed=preview_embed)
                            try:
                                details_msg = await self.bot.wait_for('message', timeout=60, check=check)
                            except asyncio.TimeoutError:
                                details_msg = None
                            await utils.safe_delete(details_want)
                            if not details_msg:
                                error = _("took too long to respond")
                                await error_msg(error)
                                return
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
                            elif details_msg.clean_content.lower() == "n" or details_msg.clean_content.lower() == "none":
                                details = ""
                            elif details_msg:
                                details = details_msg.clean_content
                    await self.send_trade(ctx, wanted_pokemon, str(offered_pokemon), details)
                    first_listing = False
                break

    async def send_trade(self, ctx, wanted_pokemon, offered_pokemon, details):
        trade_dict = self.bot.guild_dict[ctx.guild.id].setdefault('trade_dict', {})
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[ctx.channel.guild.id]['configure_dict']['settings']['offset'])).strftime(_('%I:%M %p (%H:%M)'))
        trade_stop =  ctx.bot.custom_emoji.get('trade_stop', u'\U000023f9\U0000fe0f')
        info_emoji = ctx.bot.custom_emoji.get('trade_info', u'\U00002139\U0000fe0f')
        report_emoji = ctx.bot.custom_emoji.get('trade_report', u'\U0001F4E2')
        search_emoji = ctx.bot.custom_emoji.get('trade_search', u'\U0001f50d')
        list_emoji = ctx.bot.custom_emoji.get('list_emoji', u'\U0001f5d2\U0000fe0f')
        react_list = [trade_stop, info_emoji, report_emoji, search_emoji, list_emoji]
        if not wanted_pokemon or "open trade" in wanted_pokemon:
            wanted_pokemon = "Open Trade (DM User)"
        else:
            wanted_pokemon = [f'{self.emoji_dict[i+1]}: {pkmn}' for i, pkmn in enumerate(wanted_pokemon)]
            wanted_pokemon = '\n'.join(wanted_pokemon)
        offered_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, offered_pokemon)
        if offered_pokemon.gender and (offered_pokemon.shiny or offered_pokemon.shadow):
            details = f"{offered_pokemon.gender.title()} {offered_pokemon.name.title()}. {details}"
            offered_pokemon.gender = False
        trade_embed = discord.Embed(colour=ctx.guild.me.colour)
        trade_embed.set_author(name="Pokemon Trade - {}".format(ctx.author.display_name), icon_url="https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/trade_icon_small.png")
        trade_embed.add_field(name="**Wants:**", value=wanted_pokemon, inline=True)
        trade_embed.add_field(name="**Offers:**", value=str(offered_pokemon), inline=True)
        if details and details.lower() != "none":
            trade_embed.add_field(name="Details", value=details, inline=False)
        trade_embed.set_footer(text=f"Listed by @{ctx.author.display_name} - {timestamp}", icon_url=ctx.author.avatar_url_as(format=None, static_format='png', size=256))
        trade_embed.set_thumbnail(url=offered_pokemon.img_url)
        trainercode = None
        if ctx.author.id in ctx.bot.guild_dict[ctx.guild.id].get('trainers', {}):
            trainercode = ctx.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id].get('trainercode', None)
        offered_pokemon_str = f"Meowth! {ctx.author.mention} {'(trainercode: **'+trainercode+'**) ' if trainercode else ''}offers a {str(offered_pokemon)} up for trade!"
        if "open trade" not in wanted_pokemon.lower():
            instructions = "React to this message to make an offer!"
        else:
            instructions = f"DM {ctx.author.display_name} to make an offer!"
        instructions += f"\n\n{ctx.author.display_name} can use {trade_stop} to cancel or {info_emoji} to edit details. Everyone can use {report_emoji} to report new, {search_emoji} to list desired pokemon, or {list_emoji} to list all active trades!"
        ctx.tradereportmsg = await ctx.send(f"{offered_pokemon_str} {instructions}", embed=trade_embed)
        if "open trade" not in wanted_pokemon.lower():
            for i in range(len(wanted_pokemon.split('\n'))):
                await asyncio.sleep(0.25)
                await utils.safe_reaction(ctx.tradereportmsg, f'{self.emoji_dict[i+1]}')
        for reaction in react_list:
            await asyncio.sleep(0.25)
            await utils.safe_reaction(ctx.tradereportmsg, reaction)
        dm_dict = await self.send_dm_messages(ctx, str(offered_pokemon), copy.deepcopy(trade_embed))
        ctx.bot.guild_dict[ctx.guild.id]['trade_dict'][ctx.tradereportmsg.id] = {
            'exp':time.time() + 30*24*60*60,
            'status':"active",
            'lister_id': ctx.author.id,
            'report_channel_id': ctx.channel.id,
            'report_channel':ctx.channel.id,
            'guild_id': ctx.guild.id,
            'report_guild':ctx.guild.id,
            'wanted_pokemon': wanted_pokemon,
            'offered_pokemon': str(offered_pokemon),
            'offers':{},
            'details':details,
            'dm_dict':dm_dict
        }

    async def send_dm_messages(self, ctx, trade_pokemon, embed, dm_dict=None):
        if not dm_dict:
            dm_dict = {}
        if embed:
            if isinstance(embed.description, discord.embeds._EmptyEmbed):
                embed.description = ""
            if "Jump to Message" not in embed.description:
                embed.description = embed.description + f"\n**Report:** [Jump to Message]({ctx.tradereportmsg.jump_url})"
            index = 0
            for field in embed.fields:
                if "reaction" in field.name.lower():
                    embed.remove_field(index)
                else:
                    index += 1
        delete_emoji = self.bot.config.custom_emoji.get('delete_dm', u'\U0001f5d1\U0000fe0f')
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, trade_pokemon)
        content = f"Meowth! {ctx.author.display_name} offers a {str(trade_pokemon)} up for trade in {ctx.channel.mention}! Use {delete_emoji} if you aren't interested."
        for trainer in copy.deepcopy(self.bot.guild_dict[ctx.guild.id].get('trainers', {})):
            if trainer == ctx.author.id:
                continue
            user_link = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('settings', {}).setdefault('link', True)
            if user_link:
                user_wants = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('wants', [])
                user_forms = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('forms', [])
                pokemon_setting = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].get('alerts', {}).get('settings', {}).get('categories', {}).get('pokemon', {}).get('trade', False)
            else:
                user_wants = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('trades', [])
                user_forms = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('trade_forms', [])
                pokemon_setting = True
            if not any([pokemon_setting]):
                continue
            if not checks.dm_check(ctx, trainer) or trainer in dm_dict:
                continue
            send_trade = False
            if pokemon_setting and pokemon and (pokemon.id in user_wants or str(pokemon) in user_forms):
                send_trade = True
            if send_trade:
                try:
                    user = ctx.guild.get_member(trainer)
                    tradedmmsg = await user.send(content=content, embed=embed)
                    await utils.safe_reaction(tradedmmsg, delete_emoji)
                    dm_dict[user.id] = tradedmmsg.id
                except:
                    continue
        return dm_dict

def setup(bot):
    bot.add_cog(Trading(bot))

def teardown(bot):
    bot.remove_cog(Trading)
