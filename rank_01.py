# -*- coding: utf-8 -*-
"""
rank_01.py — Падальщик у края
Натуфийская культура, ~13 000 до н. э.
Старт: 21 апреля 2026
"""

RANK = {
    "id": 1,
    "name": "Падальщик у края",
    "era": "natuf",
    "deeds_needed": 17,

    "short": "Ты — не человек. Ты — ресурс, который ещё дышит.",

    "full": (
        "Ты — не человек. Ты — ресурс, который ещё дышит. "
        "Ешь кости, разгрызённые стаями, и объедки после готовки. "
        "Спишь в яме с отбросами или за периметром, где ходят шакалы. "
        "Если заболеешь или сломаешь ногу — тебя не вылечат. "
        "Тебя используют как приманку для гиен или просто перережут горло, "
        "чтобы не тратить на тебя воздух. "
        "Убийство тебя — не преступление, а уборка мусора."
    ),

    "image_prompt": (
        "Первобытный человек у края мезолитической стоянки ночью, "
        "ест объедки с костей, большой костёр вдали, силуэты шакалов на горизонте, "
        "Левант ~12000 до н.э., реализм, мрачная атмосфера, тёмные тона"
    ),

    "done_phrases": [
        "Тебя не убили. Это почти похвала.",
        "Объедки стали чуть больше. Ты заработал.",
        "Не убили. Значит — польза была.",
        "Ты — расходный материал. Но пока нужный.",
        "Дело сделано. Никто не заметил. Это и есть твоя жизнь.",
        "Живёшь. Значит — сделал достаточно.",
        "За периметром не съели. Хороший день.",
        "Кость досталась тебе. Ты поработал.",
        "Ещё один день пережит. По-другому это не назвать.",
        "Ты полезен. Пока полезен — живёшь.",
    ],

    "promotion_text": (
        "Тебя заметили. Не убили при дележе добычи.\n"
        "Это не доброта — это расчёт.\n"
        "Ты поднимаешься с уровня отбросов.\n\n"
        "Теперь тебя не назовут «этот» — назовут «тот, что копает».\n"
        "Разница невелика. Но это шаг."
    ),

    # Дополнительные дофамин-фразы для этого ранга (древняя половина)
    "extra_dopamine": [
        ("🍖 Поесть нормально",       "🦴 Тебе бросили кость с мясом — сегодня ты в милости"),
        ("🔥 Погреться у костра",     "🔥 Тебя пустили ближе к огню — значит, ты нужен"),
        ("🌙 Лечь спать пораньше",    "🌿 Тебе дали место у края навеса — не на улице"),
        ("💧 Попить воды нормально",  "💧 Ты добрался до источника раньше шакалов"),
    ],

    # Тематика дел для этого ранга (подсказка для утренних сообщений)
    "work_context": (
        "Ты на дне. Твои дела — это выживание: "
        "сделай что просят, не возражай, будь полезен прямо сейчас."
    ),

    # Специальное сообщение при достижении 50% прогресса
    "halfway_text": (
        "⚒️ Половина пути к следующему рангу.\n"
        "9 дел позади. 8 впереди.\n"
        "Ты всё ещё живёшь за периметром. Но тебя уже не путают с шакалами."
    ),
    "products": [
        (
            "обглоданную кость с остатками мяса",
            "A gnawed animal bone with scraps of dried meat, lying on dirt at the edge of a prehistoric campsite at night, firelight far in background, jackals silhouettes, Natufian ~12000 BC, photorealistic, dark gritty atmosphere"
        ),
        (
            "кремнёвый скол, найденный у кострища",
            "A rough flint flake found near a campfire pit, lying in the dirt, prehistoric Natufian site night, firelight glow, survival object, photorealistic, ~12000 BC"
        ),
        (
            "пучок диких кореньев",
            "A bundle of wild roots and tubers gathered by hand, lying on bare earth, Natufian campsite, dawn light, foraging, photorealistic, ~12000 BC"
        ),
        (
            "засохшую шкуру животного",
            "A dried animal hide left at the edge of camp, rough and stiff, Natufian ~12000 BC, night, firelight distant, gritty realism"
        ),
        (
            "горсть диких зёрен",
            "A handful of wild grain seeds cupped in weathered hands, Natufian campsite, firelight, ~12000 BC, photorealistic, survival"
        ),
    ],

    "rare_products": [
        (
            "кусок обсидиана — редкая находка",
            "A sharp piece of black obsidian found at the edge of camp, gleaming in firelight, rare treasure for a scavenger, Natufian ~12000 BC, dramatic lighting, photorealistic"
        ),
        (
            "целую тушку мелкого зверя",
            "A small dead animal — a hare or rodent — caught by a desperate scavenger near a Natufian campsite, firelight, ~12000 BC, raw survival, photorealistic"
        ),
    ],

}
