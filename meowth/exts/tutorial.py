import asyncio
import copy
import logging

import discord
from discord.ext import commands, tasks


from meowth import checks
from meowth.exts import trade
from meowth.exts import utilities as utils

logger = logging.getLogger("meowth")

class Tutorial(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tutorial_cleanup.start()

    def cog_unload(self):
        self.tutorial_cleanup.cancel()

    async def create_tutorial_channel(self, ctx):
        ows = {
            ctx.guild.default_role: discord.PermissionOverwrite(
                read_messages=False),
            ctx.author: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                manage_channels=True),
            ctx.guild.me: discord.PermissionOverwrite(
                read_messages=True)
            }
        name = utils.sanitize_channel_name(ctx.author.display_name+"-tutorial")
        tutorial_channel = await ctx.guild.create_text_channel(
            name, overwrites=ows)
        await utils.safe_delete(ctx.message)
        await ctx.send(
            ("Meowth! I've created a private tutorial channel for "
             f"you! Continue in {tutorial_channel.mention}"),
            delete_after=30)
        return tutorial_channel

    async def delete_tutorial_channel(self, ctx):
        try:
            await ctx.tutorial_channel.delete()
        except (discord.errors.Forbidden, discord.errors.NotFound, discord.errors.HTTPException):
            pass
        try:
            del self.bot.guild_dict[ctx.guild.id]['configure_dict']['tutorial']['report_channels'][ctx.tutorial_channel.id]
        except KeyError:
            pass

    async def wait_for_cmd(self, tutorial_channel, newbie, command_name):

        # build check relevant to command
        def check(c):
            if not c.channel == tutorial_channel:
                return False
            if not c.author == newbie:
                return False
            if c.command.name == command_name:
                return True
            return False

        # wait for the command to complete
        cmd_ctx = await self.bot.wait_for(
            'command_completion', check=check, timeout=300)

        return cmd_ctx

    async def wait_for_msg(self, tutorial_channel, author):
        # build check relevant to command
        def check(c):
            if not c.channel == tutorial_channel:
                return False
            if not c.author == author:
                return False
            return True
        # wait for the command to complete
        cmd_ctx = await self.bot.wait_for(
            'message', check=check, timeout=300)
        return cmd_ctx

    @tasks.loop(seconds=21600)
    async def tutorial_cleanup(self, loop=True):
        logger.info('------ BEGIN ------')
        count = 0
        for guild in list(self.bot.guilds):
            tutorial_dict = self.bot.guild_dict[guild.id]['configure_dict'].setdefault('tutorial', {}).setdefault('report_channels', {})
            for channelid in tutorial_dict:
                channel_exists = self.bot.get_channel(channelid)
                if not channel_exists:
                    try:
                        del self.bot.guild_dict[guild.id]['configure_dict']['tutorial']['report_channels'][channelid]
                    except KeyError:
                        pass
                    try:
                        del self.bot.guild_dict[guild.id]['configure_dict']['raid']['category_dict'][channelid]
                    except KeyError:
                        pass
                else:
                    newbie = False
                    ctx = False
                    for overwrite in channel_exists.overwrites:
                        if isinstance(overwrite, discord.Member):
                            if not overwrite.bot:
                                newbie = overwrite
                                break
                    try:
                        tutorial_message = await channel_exists.fetch_message(tutorial_dict[channelid])
                    except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                        pass
                    if tutorial_message:
                        ctx = await self.bot.get_context(tutorial_message)
                    if ctx and newbie:
                        count += 1
                        ctx.author = newbie
                        ctx.tutorial_channel = channel_exists
                        if not ctx.prefix:
                            prefix = self.bot._get_prefix(self.bot, ctx.message)
                            ctx.prefix = prefix[-1]
                        try:
                            await ctx.tutorial_channel.send(f"Hey {newbie.mention} I think we were cut off due to a disconnection, let's try to start over.")
                        except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                            pass
                        ctx.bot.loop.create_task(self._tutorial(ctx, ""))
        logger.info(f"------ END - {count} Tutorials Cleaned ------")
        if not loop:
            return

    @tutorial_cleanup.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    @commands.group(case_insensitive=True, invoke_without_command=True)
    async def tutorial(self, ctx, *, tutorial_list: str=""):
        """Launches an interactive tutorial session for Meowth.

        Usage: !tutorial
        Meowth will create a private channel and initiate a
        conversation that walks you through the various commands
        that are enabled on the current server."""
        try:
            ctx.tutorial_channel = await self.create_tutorial_channel(ctx)
            await self._tutorial(ctx, tutorial_list)
        except:
            return

    async def _tutorial(self, ctx, tutorial_list):
        guild = ctx.message.guild
        cfg = self.bot.guild_dict[ctx.guild.id]['configure_dict']
        enabled = [k for k, v in cfg.items() if v.get('enabled', False)]
        no_tutorial = ['welcome', 'counters', 'archive', 'meetup']
        enabled = list(set(enabled) - set(no_tutorial))
        tutorial_reply_list = []
        tutorial_error = False
        if tutorial_list:
            tutorial_list = tutorial_list.lower().split(",")
            tutorial_list = [x.strip().lower() for x in tutorial_list]
            diff =  set(tutorial_list) - set(enabled)
            if diff and "all" in diff:
                tutorial_reply_list = enabled
            elif not diff:
                tutorial_reply_list = tutorial_list
            else:
                await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("I'm sorry, I couldn't understand some of what you entered. Let's just start here.")))
        tutorial_message = f"I created this private channel that only you can see to teach you about the server commands! You can abandon this tutorial at any time and I'll delete this channel after five minutes.\n\nJust so you know, across all of Meowth, **<> denote required arguments, [] denote optional arguments** and you don't type the <>s or []s.\n\nLet's get started!"
        if not tutorial_reply_list:
            tutorial_message += _("\n\n**Welcome**\nYou can either get a tutorial for everything by replying with **all** or reply with a comma separated list of the following Enabled Commands to get tutorials for those commands. Example: `want, raid, wild`")
            tutorial_message += _("\n\n**Enabled Commands:**\n{enabled}").format(enabled=", ".join(enabled))
            msg = await ctx.tutorial_channel.send(f"Hi {ctx.author.mention}! I'm Meowth, a Discord helper bot for Pokemon Go communities!", embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=tutorial_message).set_author(name=_('Meowth Tutorial - {guild}').format(guild=ctx.guild.name), icon_url=self.bot.user.avatar_url))
            report_channels = cfg.setdefault('tutorial', {}).setdefault('report_channels', {})
            report_channels[ctx.tutorial_channel.id] = msg.id
            while True:
                try:
                    tutorial_reply = await self.wait_for_msg(ctx.tutorial_channel, ctx.author)
                except asyncio.TimeoutError:
                    await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.red(), description=f"You took too long! This channel will be deleted in ten seconds."))
                    await asyncio.sleep(10)
                    await self.delete_tutorial_channel(ctx)
                    return
                if "all" in tutorial_reply.content.lower():
                    tutorial_reply_list = enabled
                    break
                else:
                    tutorial_reply_list = tutorial_reply.content.lower().split(",")
                    tutorial_reply_list = [x.strip() for x in tutorial_reply_list]
                    for tutorial_replyitem in tutorial_reply_list:
                        if tutorial_replyitem not in enabled:
                            tutorial_error = True
                            break
                if tutorial_error:
                    await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("I'm sorry I don't understand. Please reply with the choices above.")))
                    continue
                else:
                    break
        else:
            msg = await ctx.tutorial_channel.send(f"Hi {ctx.author.mention}! I'm Meowth, a Discord helper bot for Pokemon Go communities!", embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=tutorial_message).set_author(name=_('Meowth Configuration - {guild}').format(guild=ctx.guild.name), icon_url=self.bot.user.avatar_url))
            report_channels = cfg.setdefault('tutorial', {}).setdefault('report_channels', {})
            report_channels[ctx.tutorial_channel.id] = msg.id
        try:
            # start want tutorial
            if 'want' in tutorial_reply_list:
                completed = await self.want_tutorial(ctx, cfg)
                if not completed:
                    return

            # start wild tutorial
            if 'wild' in tutorial_reply_list:
                completed = await self.wild_tutorial(ctx, cfg)
                if not completed:
                    return

            # start raid
            if 'raid' in tutorial_reply_list:
                completed = await self.raid_tutorial(ctx, cfg)
                if not completed:
                    return

            # start exraid
            if 'exraid' in tutorial_reply_list:
                invitestr = ""

                if 'invite' in tutorial_reply_list:
                    invitestr = (
                        "The text channels that are created with this command "
                        f"are read-only until members use the **{ctx.prefix}invite** "
                        "command.")

                await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This server utilizes the **{ctx.prefix}exraid** command to report EX raids! When you use it, I will send a message summarizing the report and create a text channel for coordination. {invitestr}\n\nDue to the longer-term nature of EX raid channels, we won't try this command out right now.").set_author(name="EX Raid Tutorial", icon_url=self.bot.user.avatar_url))

            # start research
            if 'research' in tutorial_reply_list:
                completed = await self.research_tutorial(ctx, cfg)
                if not completed:
                    return

            # start lure
            if 'lure' in tutorial_reply_list:
                completed = await self.lure_tutorial(ctx, cfg)
                if not completed:
                    return

            # start invasion
            if 'invasion' in tutorial_reply_list:
                completed = await self.invasion_tutorial(ctx, cfg)
                if not completed:
                    return

            # start pvp
            if 'pvp' in tutorial_reply_list:
                completed = await self.pvp_tutorial(ctx, cfg)
                if not completed:
                    return

            # start nest
            if 'nest' in tutorial_reply_list:
                completed = await self.nest_tutorial(ctx, cfg)
                if not completed:
                    return

            # start trade
            if 'trade' in tutorial_reply_list:
                completed = await self.trade_tutorial(ctx, cfg)
                if not completed:
                    return

            # start team
            if 'team' in tutorial_reply_list:
                completed = await self.team_tutorial(ctx, cfg)
                if not completed:
                    return

            # finish tutorial
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This concludes the Meowth tutorial! This channel will be deleted in 30 seconds."))

            await asyncio.sleep(30)
        except (discord.errors.NotFound, discord.errors.HTTPException, discord.errors.Forbidden):
            await self.delete_tutorial_channel(ctx)
        finally:
            await self.delete_tutorial_channel(ctx)

    @tutorial.command(name='all')
    async def tutorial_all(self, ctx):
        """All tutorials"""
        try:
            ctx.tutorial_channel = await self.create_tutorial_channel(ctx)
            await self._tutorial(ctx, "all")
        except Exception as e:
            print(e)
            await self.delete_tutorial_channel(ctx)

    @tutorial.command()
    @checks.feature_enabled('want')
    async def want(self, ctx):
        """Launches an tutorial session for the want feature.

        Meowth will create a private channel and initiate a
        conversation that walks you through the various commands
        that are enabled on the current server."""
        try:
            ctx.tutorial_channel = await self.create_tutorial_channel(ctx)

            # get tutorial settings
            cfg = self.bot.guild_dict[ctx.guild.id]['configure_dict']

            tutorial_message = f"I created this private channel that only you can see to teach you about the server commands! You can abandon this tutorial at any time and I'll delete this channel after five minutes.\n\nJust so you know, across all of Meowth, **<> denote required arguments, [] denote optional arguments** and you don't type the <>s or []s.\n\nLet's get started!"
            await ctx.tutorial_channel.send(f"Hi {ctx.author.mention}! I'm Meowth, a Discord helper bot for Pokemon Go communities!", embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=tutorial_message).set_author(name=_('Meowth Tutorial - {guild}').format(guild=ctx.guild.name), icon_url=self.bot.user.avatar_url))
            completed = await self.want_tutorial(ctx, cfg)
            if completed:
                await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This concludes the Meowth tutorial! This channel will be deleted in 30 seconds."))
                await asyncio.sleep(30)
        except:
            await self.delete_tutorial_channel(ctx)
        finally:
            await self.delete_tutorial_channel(ctx)

    async def want_tutorial(self, ctx, config):
        try:
            report_channels = config.setdefault('tutorial', {}).setdefault('report_channels', {})

            msg_text = f"This server utilizes the **{ctx.prefix}want** command to help members receive push notifications about Pokemon and other things they want! I keep your list saved and then send you a DM for wild spawns, nest spawns, and research reports. For raid bosses I will @mention you. Please make sure you have DMs enabled in order to receive alerts!"
            msg_text += f"\n\nTry the want command by sending **{ctx.prefix}want** and following the prompts. You can use Pokemon and then Unown in this example."
            msg = await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(),description=msg_text).set_author(name="Want Tutorial", icon_url=ctx.bot.user.avatar_url))

            report_channels[ctx.tutorial_channel.id] = msg.id

            await self.wait_for_cmd(ctx.tutorial_channel, ctx.author, 'want')

            # acknowledge and wait a second before continuing
            want_channels = self.bot.guild_dict[ctx.guild.id]['configure_dict']['want']['report_channels']
            newline = "\n"
            msg = f"in the following channel{'s:'+newline if len(want_channels) > 1 else ': '}"
            counter = 0
            for c in want_channels:
                channel = discord.utils.get(ctx.guild.channels, id=c)
                perms = ctx.author.permissions_in(channel)
                if not perms.read_messages:
                    continue
                if counter > 0:
                    msg += '\n'
                if channel:
                    msg += channel.mention
                else:
                    msg += '\n#deleted-channel'
                counter += 1
            await ctx.tutorial_channel.send(embed=discord.Embed(
                colour=discord.Colour.green(),
                description=f"Great job! To undo any of your subscriptions after this tutorial, you can use **{ctx.prefix}unwant** in {msg}"))
            await asyncio.sleep(1)

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await ctx.tutorial_channel.send(embed=discord.Embed(
                colour=discord.Colour.red(),
                description=f"You took too long to complete the **{ctx.prefix}want** command! This channel will be deleted in ten seconds."))
            await asyncio.sleep(10)

            return False
        except:
            await self.delete_tutorial_channel(ctx)

        # clean up by removing tutorial from report channel config
        finally:
            try:
                del report_channels[ctx.tutorial_channel.id]
            except KeyError:
                pass

        return True

    @tutorial.command()
    @checks.feature_enabled('wild')
    async def wild(self, ctx):
        """Launches an tutorial session for the wild feature.

        Meowth will create a private channel and initiate a
        conversation that walks you through wild command."""
        try:
            ctx.tutorial_channel = await self.create_tutorial_channel(ctx)

            # get tutorial settings
            cfg = self.bot.guild_dict[ctx.guild.id]['configure_dict']

            tutorial_message = f"I created this private channel that only you can see to teach you about the server commands! You can abandon this tutorial at any time and I'll delete this channel after five minutes.\n\nJust so you know, across all of Meowth, **<> denote required arguments, [] denote optional arguments** and you don't type the <>s or []s.\n\nLet's get started!"
            await ctx.tutorial_channel.send(f"Hi {ctx.author.mention}! I'm Meowth, a Discord helper bot for Pokemon Go communities!", embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=tutorial_message).set_author(name=_('Meowth Tutorial - {guild}').format(guild=ctx.guild.name), icon_url=self.bot.user.avatar_url))
            completed = await self.wild_tutorial(ctx, cfg)
            if completed:
                await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This concludes the Meowth tutorial! This channel will be deleted in 30 seconds."))
                await asyncio.sleep(30)
        except:
            await self.delete_tutorial_channel(ctx)
        finally:
            await self.delete_tutorial_channel(ctx)

    async def wild_tutorial(self, ctx, config):
        try:
            report_channels = config.setdefault('tutorial', {}).setdefault('report_channels', {})

            msg = await ctx.tutorial_channel.send(embed=discord.Embed(
                colour=discord.Colour.lighter_grey(),
                description=f"This server utilizes the **{ctx.prefix}wild** command to report wild spawns! When you use it, I will send a message summarizing the report and containing a link to my best guess of the spawn location. If users have **{ctx.prefix}want**ed your reported pokemon, I will DM them details.\n\nTry out the wild command by sending **{ctx.prefix}wild** and following the prompts. You can use Pikachu, downtown, and 98 for this example.").set_author(name="Wild Tutorial", icon_url=ctx.bot.user.avatar_url))

            report_channels[ctx.tutorial_channel.id] = msg.id

            wild_ctx = await self.wait_for_cmd(
                ctx.tutorial_channel, ctx.author, 'wild')

            # acknowledge and wait a second before continuing
            await ctx.tutorial_channel.send(embed=discord.Embed(
                colour=discord.Colour.green(),
                description=f"Great job!"))

            omw_emoji = ctx.bot.custom_emoji.get('wild_omw', '\U0001F3CE')
            despawn_emoji = ctx.bot.custom_emoji.get('wild_despawn', '\U0001F4A8')
            info_emoji = ctx.bot.custom_emoji.get('wild_info', '\u2139')
            catch_emoji = ctx.bot.custom_emoji.get('wild_catch', '\u26BE')

            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"The {omw_emoji} emoji adds you to a list of trainers chasing the wild spawn\nThe {despawn_emoji} emoji alerts others that it has despawned.\nThe {catch_emoji} removes you from the chasing list.\nThe {info_emoji} can be used to add wild details."))

            try:
                wild_reports = ctx.bot.guild_dict[ctx.guild.id]['trainers'][wild_ctx.author.id]['reports']['wild']
                ctx.bot.guild_dict[ctx.guild.id]['trainers'][wild_ctx.author.id]['reports']['wild'] = wild_reports - 1
            except KeyError:
                pass

            await asyncio.sleep(1)

            for report in ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict']:
                if ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][report]['report_channel'] == ctx.tutorial_channel.id:
                    await utils.expire_dm_reports(ctx.bot, ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][report].get('dm_dict', {}))

            await asyncio.sleep(1)

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.red(), description=f"You took too long to complete the **{ctx.prefix}wild** command! This channel will be deleted in ten seconds."))
            await asyncio.sleep(10)
            return False
        except:
            await self.delete_tutorial_channel(ctx)

        # clean up by removing tutorial from report channel config
        finally:
            try:
                del report_channels[ctx.tutorial_channel.id]
            except KeyError:
                pass

        return True

    @tutorial.command()
    @checks.feature_enabled('raid')
    async def raid(self, ctx):
        """Launches an tutorial session for the raid feature.

        Meowth will create a private channel and initiate a
        conversation that walks you through the raid commands."""
        try:
            ctx.tutorial_channel = await self.create_tutorial_channel(ctx)

            # get tutorial settings
            cfg = self.bot.guild_dict[ctx.guild.id]['configure_dict']

            tutorial_message = f"I created this private channel that only you can see to teach you about the server commands! You can abandon this tutorial at any time and I'll delete this channel after five minutes.\n\nJust so you know, across all of Meowth, **<> denote required arguments, [] denote optional arguments** and you don't type the <>s or []s.\n\nLet's get started!"
            await ctx.tutorial_channel.send(f"Hi {ctx.author.mention}! I'm Meowth, a Discord helper bot for Pokemon Go communities!", embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=tutorial_message).set_author(name=_('Meowth Tutorial - {guild}').format(guild=ctx.guild.name), icon_url=self.bot.user.avatar_url))
            completed = await self.raid_tutorial(ctx, cfg)
            if completed:
                await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This concludes the Meowth tutorial! This channel will be deleted in 30 seconds."))
                await asyncio.sleep(30)
        except:
            await self.delete_tutorial_channel(ctx)
        finally:
            await self.delete_tutorial_channel(ctx)

    async def raid_tutorial(self, ctx, config):
        report_channels = config.setdefault('tutorial', {}).setdefault('report_channels', {})
        if config['raid']['categories'] == "region":
            category_dict = config['raid']['category_dict']
            category_dict[tutorial_channel.id] = tutorial_channel.category_id
        tutorial_channel = ctx.tutorial_channel
        prefix = ctx.prefix
        raid_channel = None
        tier5 = str(ctx.bot.raid_info['raid_eggs']["5"]['pokemon'][0]).lower()

        async def timeout_raid(cmd):
            try:
                if raid_channel:
                    await raid_channel.send(embed=discord.Embed(colour=discord.Colour.red(), description=f"You took too long to complete the **{ctx.prefix}{cmd}** command! This channel will be deleted in ten seconds."))
                await tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.red(), description=f"You took too long to complete the **{ctx.prefix}{cmd}** command! This channel will be deleted in ten seconds."))
                await asyncio.sleep(10)
                del report_channels[tutorial_channel.id]
                if config['raid']['categories'] == "region":
                    del category_dict[tutorial_channel.id]
                if raid_channel:
                    await raid_channel.delete()
                return
            except discord.errors.NotFound:
                pass

        msg = await tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This server utilizes the **{prefix}raid** command to report raids! When you use it, I will send a message summarizing the report and create a text channel for coordination. \n\nTry reporting a raid by sending **{prefix}raid** and following the prompts. You can use {tier5}, downtown, and 40 for this example.").set_author(name="Raid Tutorial", icon_url=ctx.bot.user.avatar_url))

        report_channels[ctx.tutorial_channel.id] = msg.id

        try:
            while True:
                raid_ctx = await self.wait_for_cmd(
                    tutorial_channel, ctx.author, 'raid')

                # get the generated raid channel
                if hasattr(raid_ctx, "raid_channel"):
                    raid_channel = raid_ctx.raid_channel

                if raid_channel:
                    break
                else:
                    await timeout_raid('raid')
                    return False

                # acknowledge failure and redo wait_for
                await tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.orange(), description=f"Doesn't look like it worked. Make sure you're not missing any arguments from your raid command and try again."))

            # acknowledge and redirect to new raid channel
            await tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Great job! Let's head into the new raid channel you just created: {raid_channel.mention}"))
            await asyncio.sleep(1)

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await timeout_raid('raid')
            return False

        # post raid help info prefix, avatar, user
        helpembed = await utils.get_raid_help(
            ctx.prefix, ctx.bot.user.avatar_url)

        await raid_channel.send(
            f"This is an example of a raid channel. Here is a list of "
            "commands that can be used in here:", embed=helpembed)

        try:
            if "level" in raid_channel.name:
                egg_reports = ctx.bot.guild_dict[ctx.guild.id]['trainers'][raid_ctx.author.id]['reports']['egg']
                ctx.bot.guild_dict[ctx.guild.id]['trainers'][raid_ctx.author.id]['reports']['egg'] = egg_reports - 1
            else:
                raid_reports = ctx.bot.guild_dict[ctx.guild.id]['trainers'][raid_ctx.author.id]['reports']['raid']
                ctx.bot.guild_dict[ctx.guild.id]['trainers'][raid_ctx.author.id]['reports']['raid'] = raid_reports - 1
        except KeyError:
            pass


        await raid_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"Try expressing interest in this raid!\n\nEx: `{prefix}interested 5 m3 i1 v1` would mean 5 trainers: 3 Mystic, 1 Instinct, 1 Valor"))

        # wait for interested status update
        try:
            await self.wait_for_cmd(
                raid_channel, ctx.author, 'interested')

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await timeout_raid('interested')
            return False

        # acknowledge and continue with pauses between
        await asyncio.sleep(1)
        await raid_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Great job! To save time, you can also use **{prefix}i** as an alias for **{prefix}interested**."))

        await asyncio.sleep(1)
        await raid_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"Now try letting people know that you are on your way!\n\nEx: `{prefix}coming`"))

        # wait for coming status update
        try:
            await self.wait_for_cmd(
                raid_channel, ctx.author, 'coming')

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await timeout_raid('coming')
            return False

        # acknowledge and continue with pauses between
        await asyncio.sleep(1)
        await raid_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Great! Note that if you have already specified your party in a previous command, you do not have to again for the current raid unless you are changing it. Also, **{prefix}c** is an alias for **{prefix}coming**."))

        await asyncio.sleep(1)
        await raid_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"Now try letting people know that you have arrived at the raid!\n\nEx: `{prefix}here`"))

        # wait for here status update
        try:
            await self.wait_for_cmd(
                raid_channel, ctx.author, 'here')

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await timeout_raid('here')
            return False

        # acknowledge and continue with pauses between
        await asyncio.sleep(1)
        await raid_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Good! Please note that **{prefix}h** is an alias for **{prefix}here**"))

        await asyncio.sleep(1)
        await raid_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"Now try checking to see everyone's RSVP status for this raid!\n\nEx: `{prefix}list`"))

        # wait for list command completion
        try:
            await self.wait_for_cmd(
                raid_channel, ctx.author, 'list')

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await timeout_raid('list')
            return False

        # acknowledge and continue with pauses between
        await asyncio.sleep(1)
        await raid_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Awesome! Since no one else is on their way, try using the **{prefix}starting** command to move everyone on the 'here' list to a lobby!"))

        # wait for starting command completion
        try:
            await self.wait_for_cmd(
                raid_channel, ctx.author, 'starting')

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await timeout_raid('starting')
            return False

        # acknowledge and continue with pauses between
        await asyncio.sleep(1)
        await raid_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Great! You are now listed as being 'in the lobby', where you will remain for two minutes until the raid begins. In that time, anyone can request a backout with the **{prefix}backout** command. If the person requesting is in the lobby, the backout is automatic. If it is someone who arrived at the raid afterward, confirmation will be requested from a lobby member. When a backout is confirmed, all members will be returned to the 'here' list."))

        await asyncio.sleep(1)
        await raid_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"A couple of notes about raid channels. Meowth has partnered with Pokebattler to give you the best counters for each raid boss in every situation. You can set the weather in the initial raid report, or with the **{prefix}weather** command. You can select the moveset using the reactions in the initial counters message. If you have a Pokebattler account, you can use **{prefix}pokebattler <id>** to link them! After that, the **{prefix}counters**  command will DM you your own counters pulled from your Pokebox."))

        await asyncio.sleep(1)
        await raid_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"Last thing: if you need to update the expiry time, use **{prefix}timerset <minutes left>**\n\nFeel free to play around with the commands here for a while. When you're finished, type `{prefix}timerset 0` and the raid will expire."))

        # wait for timerset command completion
        try:
            await self.wait_for_cmd(
                raid_channel, ctx.author, 'timerset')

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await timeout_raid('timerset')
            return False

        # acknowledge and direct member back to tutorial channel
        await raid_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Great! Now return to {tutorial_channel.mention} to continue the tutorial. This channel will be deleted in ten seconds."))

        await tutorial_channel.send(f"Hey {ctx.author.mention}, once I'm done cleaning up the raid channel, the tutorial will continue here!")

        await asyncio.sleep(10)

        # remove tutorial raid channel
        await raid_channel.delete()
        raid_channel = None
        del report_channels[tutorial_channel.id]
        if config['raid']['categories'] == "region":
            del category_dict[tutorial_channel.id]

        return True

    @tutorial.command()
    @checks.feature_enabled('research')
    async def research(self, ctx):
        """Launches an tutorial session for the research feature.

        Meowth will create a private channel and initiate a
        conversation that walks you through the research command."""
        try:
            ctx.tutorial_channel = await self.create_tutorial_channel(ctx)

            # get tutorial settings
            cfg = self.bot.guild_dict[ctx.guild.id]['configure_dict']

            tutorial_message = f"I created this private channel that only you can see to teach you about the server commands! You can abandon this tutorial at any time and I'll delete this channel after five minutes.\n\nJust so you know, across all of Meowth, **<> denote required arguments, [] denote optional arguments** and you don't type the <>s or []s.\n\nLet's get started!"
            await ctx.tutorial_channel.send(f"Hi {ctx.author.mention}! I'm Meowth, a Discord helper bot for Pokemon Go communities!", embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=tutorial_message).set_author(name=_('Meowth Tutorial - {guild}').format(guild=ctx.guild.name), icon_url=self.bot.user.avatar_url))
            completed = await self.research_tutorial(ctx, cfg)
            if completed:
                await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This concludes the Meowth tutorial! This channel will be deleted in 30 seconds."))
                await asyncio.sleep(30)
        except:
            await self.delete_tutorial_channel(ctx)
        finally:
            await self.delete_tutorial_channel(ctx)

    async def research_tutorial(self, ctx, config):
        try:
            report_channels = config.setdefault('tutorial', {}).setdefault('report_channels', {})

            msg = await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This server utilizes the **{ctx.prefix}research** command to report field research tasks!\n\nTry out the research command by sending **{ctx.prefix}research** and following the prompts. You can use Downtown, Catch 10 pokemon, and Pikachu for this example.").set_author(name="Research Tutorial", icon_url=ctx.bot.user.avatar_url))

            report_channels[ctx.tutorial_channel.id] = msg.id

            # wait for research command completion
            research_ctx = await self.wait_for_cmd(
                ctx.tutorial_channel, ctx.author, 'research')

            # acknowledge and wait a second before continuing
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Great job!"))
            try:
                research_reports = ctx.bot.guild_dict[ctx.guild.id]['trainers'][research_ctx.author.id]['reports']['research']
                ctx.bot.guild_dict[ctx.guild.id]['trainers'][research_ctx.author.id]['reports']['research'] = research_reports - 1
            except KeyError:
                pass

            await asyncio.sleep(1)

            for report in ctx.bot.guild_dict[ctx.guild.id]['questreport_dict']:
                if ctx.bot.guild_dict[ctx.guild.id]['questreport_dict'][report]['report_channel'] == ctx.tutorial_channel.id:
                    await utils.expire_dm_reports(ctx.bot, ctx.bot.guild_dict[ctx.guild.id]['questreport_dict'][report].get('dm_dict', {}))

            await asyncio.sleep(1)

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.red(), description=f"You took too long to complete the **{ctx.prefix}research** command! This channel will be deleted in ten seconds."))
            await asyncio.sleep(10)
            return False
        except:
            await self.delete_tutorial_channel(ctx)

        # clean up by removing tutorial from report channel config
        finally:
            try:
                del report_channels[ctx.tutorial_channel.id]
            except KeyError:
                pass

        return True

    @tutorial.command()
    @checks.feature_enabled('lure')
    async def lure(self, ctx):
        """Launches an tutorial session for the lure feature.

        Meowth will create a private channel and initiate a
        conversation that walks you through the lure command."""
        try:
            ctx.tutorial_channel = await self.create_tutorial_channel(ctx)

            # get tutorial settings
            cfg = self.bot.guild_dict[ctx.guild.id]['configure_dict']

            tutorial_message = f"I created this private channel that only you can see to teach you about the server commands! You can abandon this tutorial at any time and I'll delete this channel after five minutes.\n\nJust so you know, across all of Meowth, **<> denote required arguments, [] denote optional arguments** and you don't type the <>s or []s.\n\nLet's get started!"
            await ctx.tutorial_channel.send(f"Hi {ctx.author.mention}! I'm Meowth, a Discord helper bot for Pokemon Go communities!", embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=tutorial_message).set_author(name=_('Meowth Tutorial - {guild}').format(guild=ctx.guild.name), icon_url=self.bot.user.avatar_url))
            completed = await self.lure_tutorial(ctx, cfg)
            if completed:
                await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This concludes the Meowth tutorial! This channel will be deleted in 30 seconds."))
                await asyncio.sleep(30)
        except:
            await self.delete_tutorial_channel(ctx)
        finally:
            await self.delete_tutorial_channel(ctx)

    async def lure_tutorial(self, ctx, config):
        try:
            report_channels = config.setdefault('tutorial', {}).setdefault('report_channels', {})

            msg = await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This server utilizes the **{ctx.prefix}lure** command to report lures!\n\nTry out the lure command by sending **{ctx.prefix}lure** and following the prompts. You can use mossy, downtown, and 10 in this example.").set_author(name="Lure Tutorial", icon_url=ctx.bot.user.avatar_url))

            report_channels[ctx.tutorial_channel.id] = msg.id

            # wait for lure command completion
            lure_ctx = await self.wait_for_cmd(
                ctx.tutorial_channel, ctx.author, 'lure')

            # acknowledge and wait a second before continuing
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Great job!"))

            await asyncio.sleep(1)

            for report in ctx.bot.guild_dict[ctx.guild.id]['questreport_dict']:
                if ctx.bot.guild_dict[ctx.guild.id]['questreport_dict'][report]['report_channel'] == ctx.tutorial_channel.id:
                    await utils.expire_dm_reports(ctx.bot, ctx.bot.guild_dict[ctx.guild.id]['questreport_dict'][report].get('dm_dict', {}))

            await asyncio.sleep(1)

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.red(), description=f"You took too long to complete the **{ctx.prefix}lure** command! This channel will be deleted in ten seconds."))
            await asyncio.sleep(10)
            return False
        except:
            await self.delete_tutorial_channel(ctx)

        # clean up by removing tutorial from report channel config
        finally:
            try:
                del report_channels[ctx.tutorial_channel.id]
            except KeyError:
                pass

        return True

    @tutorial.command()
    @checks.feature_enabled('invasion')
    async def invasion(self, ctx):
        """Launches an tutorial session for the invasion feature.

        Meowth will create a private channel and initiate a
        conversation that walks you through the invasion command."""
        try:
            ctx.tutorial_channel = await self.create_tutorial_channel(ctx)

            # get tutorial settings
            cfg = self.bot.guild_dict[ctx.guild.id]['configure_dict']

            tutorial_message = f"I created this private channel that only you can see to teach you about the server commands! You can abandon this tutorial at any time and I'll delete this channel after five minutes.\n\nJust so you know, across all of Meowth, **<> denote required arguments, [] denote optional arguments** and you don't type the <>s or []s.\n\nLet's get started!"
            await ctx.tutorial_channel.send(f"Hi {ctx.author.mention}! I'm Meowth, a Discord helper bot for Pokemon Go communities!", embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=tutorial_message).set_author(name=_('Meowth Tutorial - {guild}').format(guild=ctx.guild.name), icon_url=self.bot.user.avatar_url))
            completed = await self.invasion_tutorial(ctx, cfg)
            if completed:
                await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This concludes the Meowth tutorial! This channel will be deleted in 30 seconds."))
                await asyncio.sleep(30)
        except:
            await self.delete_tutorial_channel(ctx)
        finally:
            await self.delete_tutorial_channel(ctx)

    async def invasion_tutorial(self, ctx, config):
        try:
            report_channels = config.setdefault('tutorial', {}).setdefault('report_channels', {})

            msg = await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This server utilizes the **{ctx.prefix}invasion** command to report invasions!\n\nTry out the invasion command by sending **{ctx.prefix}invasion** and following the prompts. You can use downtown, and Bulbasaur in this example.").set_author(name="Invasion Tutorial", icon_url=ctx.bot.user.avatar_url))

            report_channels[ctx.tutorial_channel.id] = msg.id

            # wait for invasion command completion
            invasion_ctx = await self.wait_for_cmd(
                ctx.tutorial_channel, ctx.author, 'invasion')

            # acknowledge and wait a second before continuing
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Great job!"))

            await asyncio.sleep(1)

            for report in ctx.bot.guild_dict[ctx.guild.id]['questreport_dict']:
                if ctx.bot.guild_dict[ctx.guild.id]['questreport_dict'][report]['report_channel'] == ctx.tutorial_channel.id:
                    await utils.expire_dm_reports(ctx.bot, ctx.bot.guild_dict[ctx.guild.id]['questreport_dict'][report].get('dm_dict', {}))

            await asyncio.sleep(1)

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.red(), description=f"You took too long to complete the **{ctx.prefix}invasion** command! This channel will be deleted in ten seconds."))
            await asyncio.sleep(10)
            return False
        except:
            await self.delete_tutorial_channel(ctx)

        # clean up by removing tutorial from report channel config
        finally:
            try:
                del report_channels[ctx.tutorial_channel.id]
            except KeyError:
                pass

        return True

    @tutorial.command()
    @checks.feature_enabled('pvp')
    async def pvp(self, ctx):
        """Launches an tutorial session for the pvp feature.

        Meowth will create a private channel and initiate a
        conversation that walks you through the pvp command."""
        try:
            ctx.tutorial_channel = await self.create_tutorial_channel(ctx)

            # get tutorial settings
            cfg = self.bot.guild_dict[ctx.guild.id]['configure_dict']

            tutorial_message = f"I created this private channel that only you can see to teach you about the server commands! You can abandon this tutorial at any time and I'll delete this channel after five minutes.\n\nJust so you know, across all of Meowth, **<> denote required arguments, [] denote optional arguments** and you don't type the <>s or []s.\n\nLet's get started!"
            await ctx.tutorial_channel.send(f"Hi {ctx.author.mention}! I'm Meowth, a Discord helper bot for Pokemon Go communities!", embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=tutorial_message).set_author(name=_('Meowth Tutorial - {guild}').format(guild=ctx.guild.name), icon_url=self.bot.user.avatar_url))
            completed = await self.pvp_tutorial(ctx, cfg)
            if completed:
                await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This concludes the Meowth tutorial! This channel will be deleted in 30 seconds."))
                await asyncio.sleep(30)
        except:
            await self.delete_tutorial_channel(ctx)
        finally:
            await self.delete_tutorial_channel(ctx)

    async def pvp_tutorial(self, ctx, config):
        try:
            report_channels = config.setdefault('tutorial', {}).setdefault('report_channels', {})

            msg = await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This server utilizes the **{ctx.prefix}pvp** command to report PVP battle requests!\n\nTry out the pvp command by sending **{ctx.prefix}pvp** and following the prompts. You can use great, downtown, and 10 in this example.").set_author(name="PVP Tutorial", icon_url=ctx.bot.user.avatar_url))

            report_channels[ctx.tutorial_channel.id] = msg.id

            # wait for pvp command completion
            pvp_ctx = await self.wait_for_cmd(
                ctx.tutorial_channel, ctx.author, 'pvp')

            # acknowledge and wait a second before continuing
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Great job!"))

            await asyncio.sleep(1)

            for report in ctx.bot.guild_dict[ctx.guild.id]['questreport_dict']:
                if ctx.bot.guild_dict[ctx.guild.id]['questreport_dict'][report]['report_channel'] == ctx.tutorial_channel.id:
                    await utils.expire_dm_reports(ctx.bot, ctx.bot.guild_dict[ctx.guild.id]['questreport_dict'][report].get('dm_dict', {}))

            await asyncio.sleep(1)

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.red(), description=f"You took too long to complete the **{ctx.prefix}pvp** command! This channel will be deleted in ten seconds."))
            await asyncio.sleep(10)
            return False
        except:
            await self.delete_tutorial_channel(ctx)

        # clean up by removing tutorial from report channel config
        finally:
            try:
                del report_channels[ctx.tutorial_channel.id]
            except KeyError:
                pass

        return True

    @tutorial.command()
    @checks.feature_enabled('trade')
    async def trade(self, ctx):
        """Launches an tutorial session for the trade feature.

        Meowth will create a private channel and initiate a
        conversation that walks you through the trade command."""
        try:
            ctx.tutorial_channel = await self.create_tutorial_channel(ctx)

            # get tutorial settings
            cfg = self.bot.guild_dict[ctx.guild.id]['configure_dict']

            tutorial_message = f"I created this private channel that only you can see to teach you about the server commands! You can abandon this tutorial at any time and I'll delete this channel after five minutes.\n\nJust so you know, across all of Meowth, **<> denote required arguments, [] denote optional arguments** and you don't type the <>s or []s.\n\nLet's get started!"
            await ctx.tutorial_channel.send(f"Hi {ctx.author.mention}! I'm Meowth, a Discord helper bot for Pokemon Go communities!", embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=tutorial_message).set_author(name=_('Meowth Tutorial - {guild}').format(guild=ctx.guild.name), icon_url=self.bot.user.avatar_url))
            completed = await self.trade_tutorial(ctx, cfg)
            if completed:
                await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This concludes the Meowth tutorial! This channel will be deleted in 30 seconds."))
                await asyncio.sleep(30)
        except Exception as e:
            await self.delete_tutorial_channel(ctx)
        finally:
            await self.delete_tutorial_channel(ctx)

    async def trade_tutorial(self, ctx, config):
        try:
            report_channels = config.setdefault('tutorial', {}).setdefault('report_channels', {})
            trade_msg = False

            msg = await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This server utilizes the **{ctx.prefix}trade** command to list your pokemon up for trade. You can also use forms of pokemon such as `alolan vulpix`, `unown y`, or `shiny absol`.\n\nTry out the trade command by sending **{ctx.prefix}trade** and following the prompts. You can use Unown, ask, and N for this example.").set_author(name="Trade Tutorial", icon_url=ctx.bot.user.avatar_url))

            report_channels[ctx.tutorial_channel.id] = msg.id

            # wait for trade command completion
            trade_msg = await self.wait_for_cmd(
                ctx.tutorial_channel, ctx.author, 'trade')

            # acknowledge and wait a second before continuing
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Great job!"))

            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"The number emojis make an offer for that pokemon and the \u23f9 emoji cancels the listing. Other interaction will take place in DM."))

            await asyncio.sleep(1)

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.red(), description=f"You took too long to complete the **{ctx.prefix}trade** command! This channel will be deleted in ten seconds."))
            await asyncio.sleep(10)
            return False
        except Exception as e:
            print(e)
            await self.delete_tutorial_channel(ctx)

        # clean up by removing tutorial from report channel config
        finally:
            try:
                del report_channels[ctx.tutorial_channel.id]
            except KeyError:
                pass
            for trade in ctx.bot.guild_dict[ctx.guild.id]['trade_dict']:
                if ctx.bot.guild_dict[ctx.guild.id]['trade_dict'][trade]['report_channel_id'] == ctx.tutorial_channel.id:
                    del ctx.bot.guild_dict[ctx.guild.id]['trade_dict'][trade]
                    break

        return True

    @tutorial.command()
    @checks.feature_enabled('team')
    async def team(self, ctx):
        """Launches an tutorial session for the team feature.

        Meowth will create a private channel and initiate a
        conversation that walks you through the team command."""
        try:
            ctx.tutorial_channel = await self.create_tutorial_channel(ctx)

            # get tutorial settings
            cfg = self.bot.guild_dict[ctx.guild.id]['configure_dict']

            tutorial_message = f"I created this private channel that only you can see to teach you about the server commands! You can abandon this tutorial at any time and I'll delete this channel after five minutes.\n\nJust so you know, across all of Meowth, **<> denote required arguments, [] denote optional arguments** and you don't type the <>s or []s.\n\nLet's get started!"
            await ctx.tutorial_channel.send(f"Hi {ctx.author.mention}! I'm Meowth, a Discord helper bot for Pokemon Go communities!", embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=tutorial_message).set_author(name=_('Meowth Tutorial - {guild}').format(guild=ctx.guild.name), icon_url=self.bot.user.avatar_url))
            completed = await self.team_tutorial(ctx, cfg)
            if completed:
                await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This concludes the Meowth tutorial! This channel will be deleted in 30 seconds."))
                await asyncio.sleep(30)
        except:
            await self.delete_tutorial_channel(ctx)
        finally:
            await self.delete_tutorial_channel(ctx)

    async def team_tutorial(self, ctx, config):
        team_set = False
        for role in ctx.author.roles:
            if role.id in self.bot.guild_dict[ctx.guild.id]['configure_dict']['team']['team_roles'].values():
                team_set = True
        if team_set:
            msg = await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"You already have a team role set through the **{ctx.prefix}team** command. If you want to change your team, contact a moderator.").set_author(name="Team Tutorial", icon_url=ctx.bot.user.avatar_url))
            return True
        try:
            report_channels = config.setdefault('tutorial', {}).setdefault('report_channels', {})

            msg = await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This server utilizes the **{ctx.prefix}team** command to allow members to select which Pokemon Go team they belong to! Type `{ctx.prefix}team mystic` for example if you are in Team Mystic.").set_author(name="Team Tutorial", icon_url=ctx.bot.user.avatar_url))

            report_channels[ctx.tutorial_channel.id] = msg.id
            # wait for team command completion
            await self.wait_for_cmd(
                ctx.tutorial_channel, ctx.author, 'team')

            # acknowledge and wait a second before continuing
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Great job!"))
            await asyncio.sleep(1)

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.red(), description=f"You took too long to complete the **{ctx.prefix}team** command! This channel will be deleted in ten seconds."))
            await asyncio.sleep(10)
            return False
        except:
            await self.delete_tutorial_channel(ctx)

        return True

    @tutorial.command()
    @checks.feature_enabled('nest')
    async def nest(self, ctx):
        """Launches an tutorial session for the nest feature.

        Meowth will create a private channel and initiate a
        conversation that walks you through the various commands
        that are enabled on the current server."""

        try:
            ctx.tutorial_channel = await self.create_tutorial_channel(ctx)

            # get tutorial settings
            cfg = self.bot.guild_dict[ctx.guild.id]['configure_dict']

            tutorial_message = f"I created this private channel that only you can see to teach you about the server commands! You can abandon this tutorial at any time and I'll delete this channel after five minutes.\n\nJust so you know, across all of Meowth, **<> denote required arguments, [] denote optional arguments** and you don't type the <>s or []s.\n\nLet's get started!"
            await ctx.tutorial_channel.send(f"Hi {ctx.author.mention}! I'm Meowth, a Discord helper bot for Pokemon Go communities!", embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=tutorial_message).set_author(name=_('Meowth Tutorial - {guild}').format(guild=ctx.guild.name), icon_url=self.bot.user.avatar_url))
            completed = await self.nest_tutorial(ctx, cfg)
            if completed:
                await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This concludes the Meowth tutorial! This channel will be deleted in 30 seconds."))
                await asyncio.sleep(30)
        except:
            await self.delete_tutorial_channel(ctx)
        finally:
            await self.delete_tutorial_channel(ctx)

    async def nest_tutorial(self, ctx, config):
        try:
            report_channels = config.setdefault('tutorial', {}).setdefault('report_channels', {})
            ctx.bot.guild_dict[ctx.guild.id]['nest_dict'][ctx.tutorial_channel.id] = {'list': ['hershey park'], 'hershey park': {'location':'40.28784,-76.65547', 'reports':{}}}

            msg = await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This server utilizes the **{ctx.prefix}nest** command to keep track of nesting pokemon.\n\nTry the nest command by sending **{ctx.prefix}nest** and following the prompts. You can use Pikachu and Hershey Park in this example.").set_author(name="Nest Tutorial", icon_url=ctx.bot.user.avatar_url))

            report_channels[ctx.tutorial_channel.id] = msg.id
            await self.wait_for_cmd(ctx.tutorial_channel, ctx.author, 'nest')

            # acknowledge and wait a second before continuing
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Great job!"))
            await asyncio.sleep(1)

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.red(), description=f"You took too long to complete the **{ctx.prefix}nest** command! This channel will be deleted in ten seconds."))
            await asyncio.sleep(10)

            return False
        except:
            await self.delete_tutorial_channel(ctx)

        # clean up by removing tutorial from report channel config
        finally:
            try:
                del report_channels[ctx.tutorial_channel.id]
            except KeyError:
                pass
            del ctx.bot.guild_dict[ctx.guild.id]['nest_dict'][ctx.tutorial_channel.id]

        return True

def setup(bot):
    bot.add_cog(Tutorial(bot))

def teardown(bot):
    bot.remove_cog(Tutorial)
