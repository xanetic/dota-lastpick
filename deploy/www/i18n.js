"use strict";
// Lightweight i18n: RU default, EN toggle. Persisted in localStorage.
const I18N = (() => {
  const DICT = {
    en: {
      "nav.casual": "Casual", "nav.ranked": "Ranked", "nav.builds": "Builds", "nav.vsai": "vs AI", "nav.mp": "Multiplayer", "nav.lb": "Leaderboard",
      "builds.new": "New build", "builds.next": "Next build",
      "builds.q": "Whose build is this? Final items from a pro match — guess the hero.",
      "builds.who": "{player} · {res}", "builds.won": "won", "builds.lost": "lost",
      "builds.loadErr": "Could not load builds.", "builds.loading": "Loading…",
      "builds.session": "Session: {c}/{n}", "builds.account": "Account: {c}/{n} ({wr}% WR)",
      "vsai.title": "Draft against the AI", "vsai.desc": "Take turns picking a 5-hero lineup against the engine, then see whose draft is stronger.",
      "vsai.easy": "Easy", "vsai.easy.sub": "picks loosely",
      "vsai.medium": "Medium", "vsai.medium.sub": "solid drafter",
      "vsai.hard": "Hard", "vsai.hard.sub": "optimal counters",
      "vsai.start": "Start draft", "vsai.again": "New draft", "vsai.analyze": "Analyze drafts",
      "vsai.yourTurn": "Your pick · {i}/5", "vsai.aiTurn": "AI is picking…", "vsai.diffTag": "Difficulty: {d}",
      "vsai.turnPickYou": "Your turn — PICK {i}/5", "vsai.turnBanYou": "Your turn — BAN {i}/7",
      "vsai.turnPickAi": "AI is picking… ({i}/5)", "vsai.turnBanAi": "AI is banning… ({i}/7)",
      "vsai.draftDone": "Draft complete — here's the AI's final lineup", "vsai.toPositions": "Assign positions →",
      "vsai.coachTitle": "How to draft better", "vsai.coachSub": "Stronger options for your roles vs this enemy draft:",
      "vsai.coachNone": "Great draft — little to improve here!",
      "coach.counter": "counters {name}", "coach.synergy": "synergy with {name}", "coach.combo": "combo with {name}",
      "coach.meta": "stronger in the meta", "coach.role": "better fit for the role", "coach.overall": "stronger overall",
      "vsai.posTitle": "Assign positions", "vsai.posDesc": "Place each of your heroes on a role (1–5). It affects the draft rating.",
      "vsai.you": "You", "vsai.ai": "AI",
      "vsai.verdictWin": "Your draft is stronger", "vsai.verdictLose": "The AI draft is stronger", "vsai.verdictTie": "Drafts are about even",
      "vsai.scoreLine": "{me} vs {ai}", "vsai.pros": "Your edge:", "vsai.cons": "AI's edge:",
      "tag": "Dota 2 draft puzzle",
      "auth.login": "Log in", "auth.register": "Sign up", "auth.logout": "Log out",
      "auth.username": "Username", "auth.password": "Password",
      "auth.signin": "Log in", "auth.create": "Create account",
      "auth.haveAccount": "Already have an account? Log in",
      "auth.noAccount": "No account? Sign up",
      "auth.guest": "Guest", "auth.needLogin": "Log in to play ranked and climb the ladder.",

      "filter.patch": "Patch", "filter.tour": "Tournament", "btn.newgame": "New game",
      "hint1": "Hint 1 · reveal teams", "hint2": "Hint 2 · reveal players & heroes",
      "picker.title": "Who is the last pick?", "picker.pick": "Pick a hero",
      "search.ph": "Search a hero by name (just start typing)…",
      "result.correct": "Correct! The last pick was {hero}.",
      "result.wrong": "Wrong. You picked {guess}, the last pick was {hero}.",
      "outcome.won": "{team} won", "outcome.score": "{r} – {d} (R–D kills)",
      "outcome.dotabuff": "View on Dotabuff ↗",
      "noMatches": "No matches for this filter", "noMatchesHint": "Try another patch / tournament combination",

      "ranked.intro.title": "Ranked Solo",
      "ranked.intro.desc": "5 rounds. One guess each, no hints. Read the draft and name the missing pick. Climb from Herald to Immortal.",
      "ranked.start": "Start ranked run", "ranked.round": "Round {i} / {n}",
      "ranked.score": "Score: {s}", "ranked.guessPrompt": "Name the hidden pick — one shot, no hints.",
      "ranked.correct": "Correct — {hero}! +{pts}", "ranked.wrong": "Wrong — it was {hero}. {pts}",
      "ranked.verdictRight": "✓ Right — {hero}", "ranked.verdictWrong": "✗ Wrong — the answer was {hero}",
      "ranked.next": "Next round", "ranked.finishView": "See results",
      "ranked.resultTitle": "Run complete", "ranked.finalScore": "Score this run",
      "ranked.correctCount": "Correct: {c} / {n}", "ranked.ratingNow": "Rating",
      "ranked.delta": "This run: {d}", "ranked.again": "Play again", "ranked.toLb": "Leaderboard",

      "mp.title": "Play a friend (Ranked 1v1)",
      "mp.create": "Create lobby", "mp.join": "Join", "mp.codePh": "Lobby code",
      "mp.lobbyCode": "Lobby code:", "mp.share": "Share this code with your friend.",
      "mp.players": "Players", "mp.waiting": "Waiting for opponent…",
      "mp.host": "host", "mp.startMatch": "Start match", "mp.needTwo": "Need 2 players to start.",
      "mp.you": "You", "mp.opp": "Opponent", "mp.oppRound": "{name}: round {i}",
      "mp.oppDone": "{name}: finished", "mp.youWon": "You won!", "mp.youLost": "You lost",
      "mp.draw": "Draw", "mp.peerLeft": "Opponent left the lobby.", "mp.waitResult": "Waiting for the opponent to finish…",
      "mp.modeGuess": "Guess last picks", "mp.modeGuessSub": "race: who guesses more",
      "mp.modeDraft": "Draft duel", "mp.modeDraftSub": "who drafts better",
      "mp.opp": "Opponent", "mp.yourPick": "Your turn — PICK", "mp.yourBan": "Your turn — BAN",
      "mp.oppPick": "Opponent is picking…", "mp.oppBan": "Opponent is banning…",
      "mp.posDone": "Confirm positions", "mp.posWait": "Waiting for the opponent…",
      "mp.draftWin": "Your draft is stronger!", "mp.draftLose": "Opponent drafted better", "mp.draftDraw": "Even draft",
      "mp.leave": "Leave", "mp.rematch": "Back to lobbies",

      "lb.title": "Top players", "lb.rank": "#", "lb.player": "Player",
      "lb.rating": "Rating", "lb.medal": "Medal", "lb.games": "Games", "lb.wins": "Wins",
      "lb.tabRanked": "Ranked", "lb.tabBuilds": "Builds", "lb.correct": "Guessed", "lb.played": "Played", "lb.winrate": "Win rate",
      "lb.empty": "No ranked players yet. Be the first!",

      "reason.title": "Why this pick?",
      "reason.needs": "What the draft still needed",
      "reason.cands": "Model's candidate last picks",
      "reason.why": "Why this hero", "reason.whyHero": "Why {hero}",
      "reason.similar": "Teams in similar lineups picked",
      "reason.foot": "Reasoning model v1 — explains plausible draft logic from hero roles, draft needs, synergies and which heroes historically pair with this lineup. Not ground truth.",
      "reason.archeBadge": "{a} draft",
      "reason.conf": "confidence: {lvl} ({p}%)",
      "reason.conf.high": "high", "reason.conf.mid": "medium", "reason.conf.low": "low",
      "reason.wellRounded": "Draft was already well-rounded — a flex / comfort pick.",
      "reason.inTop": "Our model ranked {hero} in its top {n}.",
      "reason.notTop": "Model ranked the actual pick ({hero}) #{rank} of {total}.",
      "reason.fills": "Fills the gaps:",
      "reason.synergyWith": "Synergy with {name}:",
      "reason.meta": "Meta: heavily contested this era ({p}% pick/ban presence).",
      "reason.flex": "A flexible pick that rounded out the draft.",
      "reason.simFoot": "Across the {n} most similar historical lineups.",
      "reason.simEmpty": "No comparable historical lineups found.",
      "reason.openRole": "Open role: {role}",
      "reason.roleFit": "fills the open role ({role})",
      "reason.countersHead": "Strong into:",
      "reason.signature": "Signature of {name}: {games} games ({pct}%)",
      "reason.rankNote2": "Model ranked {hero} #{rank} of {total}.",
      "reason.metaShort": "contested this patch ({p}%)",
      "reason.metaWr": "{p}% win rate in the current meta",
      "reason.combos": "Teamfight combos:", "reason.canDo": "This draft can:", "reason.lacks": "Missing:",

      "loading": "Loading data…",
      "common.cancel": "Cancel", "common.close": "Close", "common.you": "you",
    },
    ru: {
      "nav.casual": "Обычный", "nav.ranked": "Ранкед", "nav.builds": "Билды", "nav.vsai": "против ИИ", "nav.mp": "Мультиплеер", "nav.lb": "Лидерборд",
      "builds.new": "Новый билд", "builds.next": "Следующий билд",
      "builds.q": "Чей это билд? Финальные предметы из про-матча — угадай героя.",
      "builds.who": "{player} · {res}", "builds.won": "победа", "builds.lost": "поражение",
      "builds.loadErr": "Не удалось загрузить билды.", "builds.loading": "Загрузка…",
      "builds.session": "Сессия: {c}/{n}", "builds.account": "Аккаунт: {c}/{n} ({wr}% угадано)",
      "vsai.title": "Драфт против ИИ", "vsai.desc": "По очереди пикаете состав из 5 героев против движка, в конце смотрите, чей драфт сильнее.",
      "vsai.easy": "Лёгкий", "vsai.easy.sub": "пикает как попало",
      "vsai.medium": "Средний", "vsai.medium.sub": "крепкий драфтер",
      "vsai.hard": "Сложный", "vsai.hard.sub": "идеальные контрпики",
      "vsai.start": "Начать драфт", "vsai.again": "Новый драфт", "vsai.analyze": "Разобрать драфты",
      "vsai.yourTurn": "Твой пик · {i}/5", "vsai.aiTurn": "ИИ выбирает…", "vsai.diffTag": "Сложность: {d}",
      "vsai.turnPickYou": "Твой ход — ПИК {i}/5", "vsai.turnBanYou": "Твой ход — БАН {i}/7",
      "vsai.turnPickAi": "ИИ пикает… ({i}/5)", "vsai.turnBanAi": "ИИ банит… ({i}/7)",
      "vsai.draftDone": "Драфт готов — вот финальный состав ИИ", "vsai.toPositions": "Расставить позиции →",
      "vsai.coachTitle": "Как драфтить лучше", "vsai.coachSub": "Что было бы сильнее на твоих ролях против этого состава:",
      "vsai.coachNone": "Отличный драфт — тут почти нечего улучшать!",
      "coach.counter": "контрит {name}", "coach.synergy": "синергия с {name}", "coach.combo": "связка с {name}",
      "coach.meta": "сильнее в мете", "coach.role": "лучше подходит на роль", "coach.overall": "сильнее по драфту",
      "vsai.posTitle": "Расставь позиции", "vsai.posDesc": "Поставь каждого своего героя на роль (1–5). Это влияет на оценку драфта.",
      "vsai.you": "Ты", "vsai.ai": "ИИ",
      "vsai.verdictWin": "Твой драфт сильнее", "vsai.verdictLose": "Драфт ИИ сильнее", "vsai.verdictTie": "Драфты примерно равны",
      "vsai.scoreLine": "{me} против {ai}", "vsai.pros": "Твои плюсы:", "vsai.cons": "Плюсы ИИ:",
      "tag": "Драфт-головоломка по Dota 2",
      "auth.login": "Войти", "auth.register": "Регистрация", "auth.logout": "Выйти",
      "auth.username": "Логин", "auth.password": "Пароль",
      "auth.signin": "Войти", "auth.create": "Создать аккаунт",
      "auth.haveAccount": "Уже есть аккаунт? Войти",
      "auth.noAccount": "Нет аккаунта? Регистрация",
      "auth.guest": "Гость", "auth.needLogin": "Войдите, чтобы играть в ранкеде и подниматься в рейтинге.",

      "filter.patch": "Патч", "filter.tour": "Турнир", "btn.newgame": "Новая игра",
      "hint1": "Подсказка 1 · показать команды", "hint2": "Подсказка 2 · игроки и герои",
      "picker.title": "Кто последний пик?", "picker.pick": "Выбери героя",
      "search.ph": "Поиск героя по имени (просто начни печатать)…",
      "result.correct": "Верно! Последним пиком был {hero}.",
      "result.wrong": "Мимо. Ты выбрал {guess}, а последним пиком был {hero}.",
      "outcome.won": "Победа: {team}", "outcome.score": "{r} – {d} (киллы R–D)",
      "outcome.dotabuff": "Открыть на Dotabuff ↗",
      "noMatches": "Нет матчей под этот фильтр", "noMatchesHint": "Попробуй другую связку патч / турнир",

      "ranked.intro.title": "Ранкед Соло",
      "ranked.intro.desc": "5 раундов. По одной попытке, без подсказок. Читай драфт и назови скрытый пик. Поднимайся от Рекрута до Титана.",
      "ranked.start": "Начать ранкед", "ranked.round": "Раунд {i} / {n}",
      "ranked.score": "Очки: {s}", "ranked.guessPrompt": "Назови скрытый пик — одна попытка, без подсказок.",
      "ranked.correct": "Верно — {hero}! +{pts}", "ranked.wrong": "Мимо — это был {hero}. {pts}",
      "ranked.verdictRight": "✓ Угадал — {hero}", "ranked.verdictWrong": "✗ Мимо — правильный ответ {hero}",
      "ranked.next": "Следующий раунд", "ranked.finishView": "Итоги",
      "ranked.resultTitle": "Заезд завершён", "ranked.finalScore": "Очки за заезд",
      "ranked.correctCount": "Угадано: {c} / {n}", "ranked.ratingNow": "Рейтинг",
      "ranked.delta": "За этот заезд: {d}", "ranked.again": "Играть снова", "ranked.toLb": "Лидерборд",

      "mp.title": "Игра с другом (Ранкед 1 на 1)",
      "mp.create": "Создать лобби", "mp.join": "Войти", "mp.codePh": "Код лобби",
      "mp.lobbyCode": "Код лобби:", "mp.share": "Передай этот код другу.",
      "mp.players": "Игроки", "mp.waiting": "Ждём соперника…",
      "mp.host": "хост", "mp.startMatch": "Начать матч", "mp.needTwo": "Нужно 2 игрока.",
      "mp.you": "Ты", "mp.opp": "Соперник", "mp.oppRound": "{name}: раунд {i}",
      "mp.oppDone": "{name}: закончил", "mp.youWon": "Ты победил!", "mp.youLost": "Ты проиграл",
      "mp.draw": "Ничья", "mp.peerLeft": "Соперник покинул лобби.", "mp.waitResult": "Ждём, пока соперник доиграет…",
      "mp.modeGuess": "Угадайка ластпиков", "mp.modeGuessSub": "гонка: кто угадает больше",
      "mp.modeDraft": "Драфт-дуэль", "mp.modeDraftSub": "кто драфтит лучше",
      "mp.opp": "Соперник", "mp.yourPick": "Твой ход — ПИК", "mp.yourBan": "Твой ход — БАН",
      "mp.oppPick": "Соперник пикает…", "mp.oppBan": "Соперник банит…",
      "mp.posDone": "Подтвердить позиции", "mp.posWait": "Ждём соперника…",
      "mp.draftWin": "Твой драфт сильнее!", "mp.draftLose": "Соперник задрафтил лучше", "mp.draftDraw": "Драфты равны",
      "mp.leave": "Выйти", "mp.rematch": "К лобби",

      "lb.title": "Топ игроков", "lb.rank": "#", "lb.player": "Игрок",
      "lb.rating": "Рейтинг", "lb.medal": "Медаль", "lb.games": "Игры", "lb.wins": "Победы",
      "lb.tabRanked": "Ранкед", "lb.tabBuilds": "Билды", "lb.correct": "Угадано", "lb.played": "Сыграно", "lb.winrate": "Винрейт",
      "lb.empty": "Пока нет рейтинговых игроков. Будь первым!",

      "reason.title": "Почему этот пик?",
      "reason.needs": "Чего драфту не хватало",
      "reason.cands": "Кандидаты модели на ластпик",
      "reason.why": "Почему этот герой", "reason.whyHero": "Почему {hero}",
      "reason.similar": "В похожих составах брали",
      "reason.foot": "Модель рассуждений v1 — объясняет вероятную логику драфта через роли героев, потребности, синергии и то, кто исторически сочетается с этим составом. Не истина в последней инстанции.",
      "reason.archeBadge": "Драфт: {a}",
      "reason.conf": "уверенность: {lvl} ({p}%)",
      "reason.conf.high": "высокая", "reason.conf.mid": "средняя", "reason.conf.low": "низкая",
      "reason.wellRounded": "Драфт уже сбалансирован — гибкий / комфортный пик.",
      "reason.inTop": "Модель поставила {hero} в свой топ-{n}.",
      "reason.notTop": "Модель поставила реальный пик ({hero}) на {rank}-е место из {total}.",
      "reason.fills": "Закрывает пробелы:",
      "reason.synergyWith": "Синергия с {name}:",
      "reason.meta": "Мета: очень востребован в ту эпоху ({p}% присутствия в пик/бан).",
      "reason.flex": "Гибкий пик, закругливший драфт.",
      "reason.simFoot": "По {n} самым похожим историческим составам.",
      "reason.simEmpty": "Похожих исторических составов не нашлось.",
      "reason.openRole": "Открытая роль: {role}",
      "reason.roleFit": "закрывает открытую роль ({role})",
      "reason.countersHead": "Силён против:",
      "reason.signature": "Сигнатурка {name}: {games} игр ({pct}%)",
      "reason.rankNote2": "Модель поставила {hero} на {rank}-е из {total}.",
      "reason.metaShort": "востребован в патче ({p}%)",
      "reason.metaWr": "{p}% винрейт в текущей мете",
      "reason.combos": "Связки в тимфайте:", "reason.canDo": "Драфт умеет:", "reason.lacks": "Не хватает:",

      "loading": "Загрузка данных…",
      "common.cancel": "Отмена", "common.close": "Закрыть", "common.you": "ты",
    },
  };

  // draft-axis labels (reasoning panel)
  const AXIS = {
    en: { frontline: "frontline", initiation: "initiation", teamfight: "teamfight",
      pickoff: "pick-off", lockdown: "lockdown / control", save_peel: "save / peel",
      tower_pressure: "tower pressure", defense_waveclear: "wave clear / anti-push",
      scaling: "late-game scaling", early_tempo: "early tempo", mobility: "mobility",
      splitpush: "split push", dmg_physical: "physical damage", dmg_magical: "magical damage",
      auras: "auras", sustain: "sustain", map_control: "map control / vision", roshan: "Roshan control" },
    ru: { frontline: "фронтлайн", initiation: "инициация", teamfight: "тимфайт",
      pickoff: "пикофф / отлов", lockdown: "контроль", save_peel: "сейв / пил",
      tower_pressure: "давление на вышки", defense_waveclear: "зачистка волн / антипуш",
      scaling: "скейл в лейт", early_tempo: "ранний темп", mobility: "мобильность",
      splitpush: "сплитпуш", dmg_physical: "физ. урон", dmg_magical: "маг. урон",
      auras: "ауры", sustain: "сустейн", map_control: "контроль карты / вижн", roshan: "контроль Рошана" },
  };
  // draft archetypes (reasoning panel)
  const ARCHE = {
    en: { "Teamfight": "Teamfight", "Deathball": "Deathball", "Pickoff": "Pickoff",
      "Split Push": "Split Push", "Protect the Carry": "Protect the Carry",
      "High Ground Defense": "High Ground Defense", "Tempo": "Tempo" },
    ru: { "Teamfight": "Тимфайт", "Deathball": "Пуш пятёркой", "Pickoff": "Пикофф",
      "Split Push": "Сплитпуш", "Protect the Carry": "Защита кэрри",
      "High Ground Defense": "Оборона хайграунда", "Tempo": "Темповый" },
  };

  // Dota rank names per language
  const MEDALS = {
    en: { Herald: "Herald", Guardian: "Guardian", Crusader: "Crusader", Archon: "Archon",
          Legend: "Legend", Ancient: "Ancient", Divine: "Divine", Immortal: "Immortal" },
    ru: { Herald: "Рекрут", Guardian: "Страж", Crusader: "Рыцарь", Archon: "Герой",
          Legend: "Легенда", Ancient: "Властелин", Divine: "Божество", Immortal: "Титан" },
  };

  let lang = localStorage.getItem("lang") || "ru";

  function t(key, vars) {
    let s = (DICT[lang] && DICT[lang][key]) || (DICT.en[key]) || key;
    if (vars) for (const k in vars) s = s.replace(new RegExp("\\{" + k + "\\}", "g"), vars[k]);
    return s;
  }
  function medalLabel(m) {
    if (!m) return "";
    const name = (MEDALS[lang] || MEDALS.en)[m.tier] || m.tier;
    return m.tier === "Immortal" ? `${name} · ${m.rating}` : `${name} ${m.star}`;
  }
  function medalName(tier) { return (MEDALS[lang] || MEDALS.en)[tier] || tier; }
  function axisLabel(key) { return (AXIS[lang] || AXIS.en)[key] || key; }
  function archetype(name) { return (ARCHE[lang] || ARCHE.en)[name] || name; }
  const ROLE = {
    en: { 1: "carry", 2: "mid", 3: "offlane", 4: "pos 4", 5: "pos 5" },
    ru: { 1: "керри", 2: "мид", 3: "офлейн", 4: "саппорт 4", 5: "саппорт 5" },
  };
  function role(pos) { return (ROLE[lang] || ROLE.en)[pos] || ("pos " + pos); }
  const EVAL = {
    en: { roles: "Role coverage", synergy: "Synergy", counter: "Counters", teamfight: "Teamfight",
          control: "Control", scaling: "Late-game", balance: "Damage balance", meta: "Meta" },
    ru: { roles: "Покрытие ролей", synergy: "Синергия", counter: "Контрпики", teamfight: "Тимфайт",
          control: "Контроль", scaling: "Лейт", balance: "Баланс урона", meta: "Мета" },
  };
  function evalAxis(key) { return (EVAL[lang] || EVAL.en)[key] || key; }
  function diffName(d) { return t("vsai." + d); }
  const COMBO_TYPE = {
    en: { setup: "setup → AoE payoff", chaininit: "chain initiation", protect: "protect the carry",
          lockcore: "lock down their core", diveandsave: "dive + save" },
    ru: { setup: "завязка → AoE-добивание", chaininit: "двойная инициация", protect: "защита кэрри",
          lockcore: "размен ядра врага", diveandsave: "дайв + сейв" },
  };
  function comboType(tp) { return (COMBO_TYPE[lang] || COMBO_TYPE.en)[tp] || tp; }
  const CONCEPT = {
    en: { initiation: "initiation", followup: "AoE damage", save: "save / peel",
          pierce: "BKB-pierce control", frontline: "frontline", lockdown: "lockdown" },
    ru: { initiation: "инициация", followup: "AoE-урон", save: "сейв / пил",
          pierce: "контроль сквозь BKB", frontline: "фронтлайн", lockdown: "контроль" },
  };
  function conceptLabel(k) { return (CONCEPT[lang] || CONCEPT.en)[k] || k; }
  function get() { return lang; }
  function set(l) { lang = l; localStorage.setItem("lang", l); apply(); document.dispatchEvent(new Event("langchange")); }

  function apply() {
    document.documentElement.lang = lang;
    document.querySelectorAll("[data-i18n]").forEach((e) => { e.textContent = t(e.getAttribute("data-i18n")); });
    document.querySelectorAll("[data-i18n-ph]").forEach((e) => { e.placeholder = t(e.getAttribute("data-i18n-ph")); });
  }

  return { t, get, set, apply, medalLabel, medalName, axisLabel, archetype, role, evalAxis, diffName, comboType, conceptLabel };
})();
