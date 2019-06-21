# bot token from discord developers
bot_token = 'token_here'

# default bot settings
default_prefix = '!'
master = 123123123123123123
bot_coowners = []
managers = [123123123123123123, 123123123123123123, 123123123123123123]

# default language
bot_language = 'en'
pokemon_language = 'en'

# team settings
team_dict = {"mystic":":mystic:", "valor":":valor:", "instinct":":instinct:", "harmony":":harmony:"}
unknown = ":grey_question:"

# raid settings
allow_assume = {"EX":"True", "5":"True", "4":"False", "3":"False", "2":"False", "1":"False"}

# status emoji
omw_id = ":omw:"
here_id = ":here:"

# type emoji; These can be custom or discord alias
# Example:  Custom: `<:emojiname:emojiid>` | Alias: `:emojiname`
type_id_dict = {
    "normal"   : "<:normal:346750029152780288>",
    "fire"     : "<:fire1:346750028863242240>",
    "water"    : "<:water:346750028733480964>",
    "electric" : "<:electric:346750028511182850>",
    "grass"    : "<:grass:346750029681262592>",
    "ice"      : "<:ice:346750029115162624>",
    "fighting" : "<:fighting:346750028817367040>",
    "poison"   : "<:poison:346750028964036619>",
    "ground"   : "<:ground:346750028767035404>",
    "flying"   : "<:flying:346750029001654272>",
    "psychic"  : "<:psychic:346750028678692866>",
    "bug"      : "<:bug1:346750028494143488>",
    "rock"     : "<:rock:346750029123551233>",
    "ghost"    : "<:ghost1:346750028406325259>",
    "dragon"   : "<:dragon1:346750028892733440>",
    "dark"     : "<:dark:346750028506988544>",
    "steel"    : "<:steel:346750029177815050>",
    "fairy"    : "<:fairy:346750028431228930>"
}

# custom_emoji for reactions and general use; These must be unicode or custom emoji. Not discord alias
# Example: Custom:`<:emojiname:emojiid>` | Standard: Use https://gist.github.com/Vexs/629488c4bb4126ad2a9909309ed6bd7
# If "surrogates" error use https://www.fileformat.info/index.htm python source code
custom_emoji = {
    'bullet': "\U0001F539",
    'research_complete' : "<:researchstamp:590524697255346178>",
    'research_expired' : "\U0001F4A8",
    'res_candy' : "<:rarecandy:590530352137764886>",
    'res_dust' : "<:stardust:590530352267919361>",
    'res_encounter' : "<:encounter:590530350946582539>",
    'res_revive' : "<:revive:590530351814934548>",
    'res_ball' : "<:pokeball:590533257716826152>",
    'res_potion' : "<:potion:590530351600762880>",
    'res_berry' : "<:berry:590530352334766081>",
    'res_other' : "<:mysteryitem:590530351844294666>",
    'raid_maybe' : "\u2753",
    'raid_omw' : "<:omw:346750028972294146>",
    'raid_here' : "<:here:393155593973530625>",
    'raid_cancel' : "\u274C",
    'raid_info' : "\u2139",
    'wild_omw' : "<:omw:346750028972294146>",
    'wild_despawn' : "\U0001F4A8",
    'wild_catch' : "<:pokeball:590533257716826152>",
    'wild_info' : "\u2139",
    'wild_bullet' : "\U0001F539",
    'trade_stop' : "\u23f9",
    'trade_accept' : "\u2705",
    'trade_reject' : "\u274e",
    'trade_complete' : "\u2611",
    'trade_bullet' : "\U0001F539",
    'answer_yes' : "\u2705",
    'answer_no' : "\u274e",
    'answer_cancel' : "\u274c",
    'command_done' : "\u2611",
    'huntr_report' : "\u2705",
    'shiny_chance' : "\u2728",
    'windy':"\U0001F343",
    'snowy':"\u2744",
    'partlycloudy':"\u26C5",
    'rainy':"\u2614",
    'foggy':"\U0001F301",
    'cloudy':"\u2601",
    'clear':"\u2600"
}
