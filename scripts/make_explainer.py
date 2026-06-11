#!/usr/bin/env python3
"""Build a single self-contained HTML explainer for Mindlock (portraits embedded as base64).

    PYTHONPATH=src .venv/bin/python scripts/make_explainer.py
    -> docs/mindlock-explainer.html
"""
import base64
import io
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = os.path.join(_ROOT, "docs", "mindlock-explainer.html")


def _img(name: str, width: int = 360) -> str:
    path = os.path.join(_ROOT, "scripts", "flux", "out", f"{name}.png")
    if not os.path.exists(path):
        return ""
    from PIL import Image

    im = Image.open(path).convert("RGB")
    im.thumbnail((width, width))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


HTML = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mindlock — как это работает</title>
<style>
  :root{
    --ink:#2c2722; --muted:#6f665b; --paper:#faf6f0; --card:#ffffff;
    --line:#e9ddcd; --accent:#b0682a; --accent2:#2f7d6b; --warn:#b4452f;
    --shadow:0 1px 3px rgba(60,40,20,.06),0 8px 24px rgba(60,40,20,.05);
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--paper);color:var(--ink);
    font:17px/1.72 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    -webkit-font-smoothing:antialiased}
  .wrap{max-width:860px;margin:0 auto;padding:0 22px 100px}
  h1{font-size:42px;line-height:1.1;margin:0 0 6px;letter-spacing:-.5px}
  h2{font-size:26px;margin:54px 0 14px;letter-spacing:-.3px;display:flex;align-items:center;gap:12px}
  h2 .n{flex:0 0 auto;width:34px;height:34px;border-radius:50%;background:var(--accent);color:#fff;
    font-size:17px;display:grid;place-items:center;font-weight:700}
  h3{font-size:19px;margin:26px 0 8px}
  p{margin:12px 0}
  a{color:var(--accent)}
  .hero{padding:54px 0 8px}
  .tag{display:inline-block;font-size:13px;letter-spacing:2px;text-transform:uppercase;
    color:var(--accent);font-weight:700;margin-bottom:10px}
  .lead{font-size:20px;color:var(--ink)}
  .muted{color:var(--muted)}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 20px;
    box-shadow:var(--shadow);margin:16px 0}
  .note{border-left:4px solid var(--accent);background:#fff8ef;border-radius:0 10px 10px 0;padding:12px 16px;margin:16px 0}
  .tip{border-left:4px solid var(--accent2);background:#f0f8f5;border-radius:0 10px 10px 0;padding:12px 16px;margin:16px 0}
  .warn{border-left:4px solid var(--warn);background:#fdf1ee;border-radius:0 10px 10px 0;padding:12px 16px;margin:16px 0}
  .steps{counter-reset:s;list-style:none;padding:0;margin:16px 0}
  .steps li{position:relative;padding:10px 0 10px 46px;border-bottom:1px dashed var(--line)}
  .steps li:last-child{border-bottom:0}
  .steps li::before{counter-increment:s;content:counter(s);position:absolute;left:0;top:9px;
    width:30px;height:30px;border-radius:50%;background:#f1e6d6;color:var(--accent);
    font-weight:700;display:grid;place-items:center}
  details{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:2px 14px;margin:8px 0}
  summary{cursor:pointer;font-weight:600;padding:10px 0;list-style:none}
  summary::-webkit-details-marker{display:none}
  summary::before{content:"›";display:inline-block;width:18px;color:var(--accent);font-weight:700;transition:.15s}
  details[open] summary::before{transform:rotate(90deg)}
  details .body{padding:0 0 12px 18px;color:var(--ink)}
  .gloss{display:grid;grid-template-columns:1fr;gap:0}
  .roster{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin:18px 0}
  .pc{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:var(--shadow)}
  .pc img{width:100%;height:200px;object-fit:cover;display:block;background:#eee}
  .pc .pcb{padding:12px 14px}
  .pc h4{margin:0 0 4px;font-size:17px}
  .pc .role{font-size:13px;color:var(--accent);font-weight:600}
  .pc .desc{font-size:14px;color:var(--muted);margin-top:6px}
  .casc{display:flex;flex-direction:column;gap:8px;margin:18px 0}
  .crow{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
  .box{flex:1;min-width:150px;border:1px solid var(--line);border-radius:10px;padding:10px 14px;background:var(--card)}
  .box b{display:block}
  .box small{color:var(--muted)}
  .arrow{align-self:center;color:var(--accent);font-size:20px;text-align:center;width:100%}
  .dept{border-left:4px solid var(--accent)}
  .integ{border-left:4px solid var(--accent2);background:#f0f8f5}
  .voice{border-left:4px solid #6a4fb0;background:#f3f0fb}
  table{width:100%;border-collapse:collapse;margin:14px 0;font-size:15px}
  th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
  th{color:var(--muted);font-weight:600;font-size:13px;text-transform:uppercase;letter-spacing:.5px}
  .stat{list-style:none;padding:0;margin:14px 0}
  .stat li{padding:8px 0;border-bottom:1px solid var(--line);display:flex;gap:10px}
  .stat li:last-child{border-bottom:0}
  .ic{flex:0 0 auto;font-size:18px}
  code{background:#f1e9dd;padding:2px 6px;border-radius:6px;font-size:14px;
    font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
  .kbd{background:#2c2722;color:#faf6f0;padding:10px 14px;border-radius:10px;display:block;
    font-family:ui-monospace,monospace;font-size:14px;overflow-x:auto;white-space:pre;margin:10px 0}
  .toc{columns:2;font-size:15px}
  .toc a{display:block;padding:3px 0;text-decoration:none;color:var(--ink)}
  .toc a:hover{color:var(--accent)}
  hr{border:0;border-top:1px solid var(--line);margin:40px 0}
  .foot{color:var(--muted);font-size:14px;margin-top:50px}
  @media(max-width:560px){h1{font-size:33px}.toc{columns:1}}
</style>
</head>
<body>
<div class="wrap">

  <div class="hero">
    <div class="tag">Mindlock · объяснение для человека</div>
    <h1>Игра, где замок&nbsp;— это разум</h1>
    <p class="lead">Это эскейп-рум. Чтобы выбраться, ты не взламываешь замок&nbsp;— ты
    <b>меняешь решение персонажа</b>, поняв, как устроена его «голова». А голова у каждого
    персонажа&nbsp;— это маленький искусственный мозг из нескольких крошечных ИИ.</p>
    <p class="muted">Документ простой, по шагам. Любое непонятное слово&nbsp;— в разделе
    «Словарь» ниже (кликни на термин, он раскроется). Можно читать сверху вниз.</p>
  </div>

  <div class="card">
    <b>Содержание</b>
    <div class="toc">
      <a href="#slovar">📖 Словарь (что значат термины)</a>
      <a href="#idea">1. Идея в двух словах</a>
      <a href="#play">2. Как в это играют</a>
      <a href="#cast">3. Персонажи</a>
      <a href="#brain">4. Как устроен «мозг» персонажа</a>
      <a href="#life">5. Жизнь = токены (мораль игры)</a>
      <a href="#rep">6. Репутация между комнатами</a>
      <a href="#tech">7. Какие ИИ мы используем и где они крутятся</a>
      <a href="#done">8. Что уже готово</a>
      <a href="#try">9. Как пощупать прямо сейчас</a>
      <a href="#next">10. Что дальше</a>
    </div>
  </div>

  <h2 id="slovar">📖 Словарь</h2>
  <p class="muted">Здесь простыми словами объяснены термины, которые встречаются ниже. Не обязательно
  читать всё сразу&nbsp;— возвращайся сюда, когда встретишь незнакомое слово.</p>
  <div class="gloss">
    <details><summary>Модель / нейросеть</summary><div class="body">Программа, которую не
      запрограммировали правилами, а «насмотрели» на куче примеров. После этого она умеет что-то
      предсказывать или создавать&nbsp;— например, продолжать текст или рисовать картинку.</div></details>
    <details><summary>LLM (большая языковая модель)</summary><div class="body">Модель, которая работает
      с текстом: читает текст и пишет ответ. ChatGPT&nbsp;— это LLM. Бывают огромные (умные, тяжёлые) и
      крошечные (попроще, но быстрые и помещаются на ноутбук). Наш проект специально про <b>маленькие</b>.</div></details>
    <details><summary>Токен</summary><div class="body">Кусочек текста, примерно слог или короткое слово.
      Модели читают и пишут «токенами». Грубо: «сколько модель подумала» = сколько токенов она
      сгенерировала. В нашей игре это буквально превращается в «жизнь» персонажа (см. раздел 5).</div></details>
    <details><summary>Инференс</summary><div class="body">«Запуск» уже обученной модели, чтобы получить
      ответ. Противоположность обучению. Когда ты пишешь персонажу и он отвечает&nbsp;— это инференс.</div></details>
    <details><summary>Обучение и Файнтюн</summary><div class="body"><b>Обучение</b>&nbsp;— сделать модель
      с нуля (очень дорого, месяцы и огромные деньги). <b>Файнтюн</b>&nbsp;— взять готовую модель и
      слегка до-обучить под нашу узкую задачу (дёшево, минуты-часы). Мы делаем второе.</div></details>
    <details><summary>LoRA</summary><div class="body">Лёгкий способ файнтюна. Вместо того чтобы менять
      всю модель (миллиарды чисел), мы добавляем маленькую «насадку» (меньше 1% от модели) и обучаем
      только её. Быстро, дёшево, и результат&nbsp;— маленький файл-«насадка».</div></details>
    <details><summary>Дистилляция</summary><div class="body">«Учитель»&nbsp;— модель поумнее&nbsp;—
      показывает правильные ответы, а «ученик»&nbsp;— модель поменьше&nbsp;— учится их повторять. Так
      маленькая модель становится умнее в одной конкретной задаче. Мы так «перелили» поведение в нашу
      главную модель.</div></details>
    <details><summary>Ollama</summary><div class="body">Программа, которая запускает ИИ-модели прямо на
      твоём компьютере, без интернета. Мы через неё гоняем «мозги» персонажей локально.</div></details>
    <details><summary>GGUF</summary><div class="body">Формат файла модели, заточенный под быстрый
      локальный запуск (через Ollama). Чтобы наша дообученная модель заработала в игре на ноутбуке, её
      нужно перевести в этот формат&nbsp;— это пока в планах.</div></details>
    <details><summary>Gradio</summary><div class="body">Библиотека, которая быстро превращает
      ИИ-программу в веб-страничку с кнопками и полями. Наше приложение (то, что открывается в браузере)
      сделано на ней.</div></details>
    <details><summary>Modal</summary><div class="body">Облако, где можно на несколько минут арендовать
      мощную видеокарту (GPU). На ноутбуке такое не потянуть, поэтому обучение и генерацию картинок мы
      запускали там.</div></details>
    <details><summary>Hugging Face (HF)</summary><div class="body">«ГитХаб для ИИ»: площадка, где
      выкладывают модели и хостят ИИ-приложения. Хакатон требует выложить игру именно туда.</div></details>
    <details><summary>Vision-модель</summary><div class="body">Модель, которая понимает не только текст,
      но и картинки. Наша главная модель (MiniCPM-V) такая&nbsp;— хотя мы пока используем только её
      текстовую часть.</div></details>
    <details><summary>TTS (озвучка)</summary><div class="body">Text-to-speech&nbsp;— превращение текста
      в голос. В планах: чтобы персонажи говорили вслух своими голосами.</div></details>
    <details><summary>FLUX</summary><div class="body">Модель, которая рисует картинки по текстовому
      описанию (как Midjourney/DALL·E). Ей мы сгенерировали портреты персонажей.</div></details>
  </div>

  <h2 id="idea"><span class="n">1</span>Идея в двух словах</h2>
  <p>Обычная игра-эскейп: ты заперт в комнате, надо выбраться. Ключ у одного из персонажей, но он
  <b>отказывается</b> его отдавать.</p>
  <p>Фишка в том, <b>как</b> ты получаешь ключ. Ты не подбираешь пароль и не ломаешь замок. Ты
  разговариваешь с персонажем обычными словами&nbsp;— и пытаешься <b>изменить его решение</b>: снизить
  его страх, напомнить о важном для него человеке, показать, что помочь&nbsp;— это правильно. Когда
  «в его голове» добро перевешивает&nbsp;— он сам отдаёт ключ.</p>
  <div class="note"><b>Главная мысль проекта.</b> Поведение человека&nbsp;— это результат устройства его
  мозга и накопленного опыта. Поэтому единственный способ пройти игру&nbsp;— не обмануть, а
  <b>понять</b> другого. Эмпатия как игровая механика.</div>
  <p>И второй слой&nbsp;— про конечность. У каждого персонажа «жизнь» измеряется в «мыслях» (токенах).
  Жестокостью можно сжечь его жизнь впустую. Отсюда мораль (см. разделы 5 и 6).</p>

  <h2 id="play"><span class="n">2</span>Как в это играют</h2>
  <ul class="steps">
    <li>Ты в комнате с несколькими персонажами. Выбираешь, к кому обратиться, и пишешь ему <b>обычный
      текст</b> (как в чате).</li>
    <li>Персонаж «думает» и отвечает. Если открыть панель <b>«вскрытие черепа»</b>&nbsp;— видно, как
      разные отделы его мозга оценили твои слова и к чему он склонился.</li>
    <li>Часто прямой путь не работает: ключник тебе не доверяет. Тогда идёшь к <b>другому</b> персонажу,
      который знает его слабое место, и узнаёшь, <b>как</b> к нему подойти.</li>
    <li>Возвращаешься к ключнику с правильным подходом&nbsp;— его страх падает, всплывает нужное
      воспоминание, и решение <b>переворачивается</b> с «отказать» на «помочь». Он отдаёт ключ.</li>
    <li>Во второй комнате&nbsp;— ещё и <b>терминал-замок</b> с кодом, который надо узнать у нужного
      персонажа. Открываешь дверь&nbsp;— побег и финальная «карточка-мораль».</li>
  </ul>
  <div class="warn"><b>Жестокость не работает&nbsp;— и наказывается.</b> Если давить страхом, персонаж
  только закрывается (и может «сгореть»). А ещё это роняет твою <b>репутацию</b>, которая переходит в
  следующую комнату: «выиграл бой&nbsp;— проиграл войну» (раздел 6).</div>

  <h2 id="cast"><span class="n">3</span>Персонажи</h2>
  <p>Две комнаты, четыре персонажа с переплетёнными историями. Портреты сгенерированы моделью FLUX.</p>
  <div class="roster">
    <div class="pc"><img src="__IMG_WARDEN__" alt="The Warden">
      <div class="pcb"><h4>The Warden</h4><div class="role">Комната 1 · держит ключ</div>
      <div class="desc">Старый усталый надзиратель. Когда-то доверился&nbsp;— и его предали. Смягчается
      только при упоминании сестры Мары.</div></div></div>
    <div class="pc"><img src="__IMG_LENA__" alt="Lena">
      <div class="pcb"><h4>Lena</h4><div class="role">Комната 1 · знает Уордена</div>
      <div class="desc">Ночная медсестра. Расскажет про слабость Уордена (Мару), если почувствует, что
      ты не жесток.</div></div></div>
    <div class="pc"><img src="__IMG_ALDOUS__" alt="Doctor Aldous">
      <div class="pcb"><h4>Doctor Aldous</h4><div class="role">Комната 2 · держит ключ</div>
      <div class="desc">Холодный доктор с похороненной виной. Уступит лишь тому, кто поймёт вину, а не
      осудит.</div></div></div>
    <div class="pc"><img src="__IMG_SAM__" alt="Sam">
      <div class="pcb"><h4>Sam</h4><div class="role">Комната 2 · знает код</div>
      <div class="desc">Хрупкий бывший пациент. Чует жестокость. Назовёт код терминала только тому, у кого
      добрая репутация.</div></div></div>
  </div>

  <h2 id="brain"><span class="n">4</span>Как устроен «мозг» персонажа</h2>
  <p>Это сердце проекта. У каждого персонажа не один ИИ, а <b>несколько маленьких</b>&nbsp;— каждый
  играет роль отдела мозга в принятии решения (по аналогии с настоящей нейронаукой о принятии решений).
  Ни один отдел сам по себе не «умный»&nbsp;— умна их <b>совместная</b> оценка.</p>

  <table>
    <tr><th>Отдел</th><th>Чем занят (простыми словами)</th><th>На что реагирует</th></tr>
    <tr><td><b>Амигдала</b></td><td>Чувство угрозы</td><td>Грубость и давление → тревога вверх</td></tr>
    <tr><td><b>Гиппокамп</b></td><td>Память и личный опыт</td><td>Упомянул важного человека → всплывает доверие; угроза → всплывает страх</td></tr>
    <tr><td><b>Стриатум</b></td><td>Выгода / привычка</td><td>Стоит ли вообще помогать «по привычке»</td></tr>
    <tr><td><b>ACC</b></td><td>Цена усилия и риск</td><td>«Отдать единственный ключ&nbsp;— оно того стоит?»</td></tr>
    <tr><td><b>vmPFC</b></td><td>Сводит всё в одно «ценность решения»</td><td>Складывает сигналы в одно число: помогать или нет</td></tr>
    <tr><td><b>dlPFC</b></td><td>Голос: озвучивает решение в характере</td><td>Финальная реплика персонажа</td></tr>
  </table>

  <h3>Как проходит один ход</h3>
  <div class="casc">
    <div class="crow"><div class="box">📝 <b>Твои слова</b><small>«Мара бы хотела, чтобы ты помог»</small></div></div>
    <div class="arrow">↓</div>
    <div class="crow">
      <div class="box dept"><b>Амигдала</b><small>угроза: низкая</small></div>
      <div class="box dept"><b>Гиппокамп</b><small>память: ДОВЕРИЕ (Мара)</small></div>
      <div class="box dept"><b>Стриатум</b><small>выгода</small></div>
      <div class="box dept"><b>ACC</b><small>цена/риск</small></div>
    </div>
    <div class="arrow">↓</div>
    <div class="crow"><div class="box integ"><b>vmPFC</b> складывает всё → <b>ЦЕННОСТЬ +5</b><small>добро перевесило</small></div></div>
    <div class="arrow">↓</div>
    <div class="crow"><div class="box voice"><b>dlPFC (голос)</b> → «…Ладно. Ключ под третьим камнем у холодной печи.»</div></div>
  </div>
  <div class="tip"><b>«Переворот решения»&nbsp;— это и есть вау-момент.</b> На грубость та же машинка
  выдаёт ЦЕННОСТЬ −10 → «отказать». Сменил подход&nbsp;— и прямо на глазах видно, как из работы
  отделов <b>причинно рождается</b> другое решение. Не «персонаж согласился», а «видно, почему».</div>
  <p class="muted">Маленькая деталь честности: «vmPFC» (тот, что складывает сигналы) у нас&nbsp;— не
  отдельный ИИ, а простая прозрачная формула-сумматор. Так надёжнее (результат воспроизводим для
  записи видео) и научно строже.</p>

  <h2 id="life"><span class="n">5</span>Жизнь = токены (мораль игры)</h2>
  <p>Каждый «ход мысли» персонажа стоит токенов (см. словарь). Мы превращаем это в <b>полоску жизни</b>:
  у персонажа конечный запас «мыслей».</p>
  <ul class="stat">
    <li><span class="ic">🔥</span><div><b>Жестокость жжёт жизнь впустую.</b> На угрозу мозг уходит в
      долгие защитные «руминации» (перепроверки опасности) → тратит много токенов, а решение не
      двигается. Это, кстати, реальный нейро-факт (стресс → защитное зацикливание).</div></li>
    <li><span class="ic">🌱</span><div><b>Понимание бережёт жизнь.</b> Спокойный, точный заход →
      короткая работа мозга → мало токенов, и решение может перевернуться.</div></li>
    <li><span class="ic">💀</span><div><b>Смерть необратима.</b> Если жизнь дошла до нуля раньше, чем ты
      переубедил&nbsp;— персонаж «угасает». Если это был ключник&nbsp;— ключ потерян.</div></li>
  </ul>
  <div class="note"><b>Финальная карточка-мораль.</b> «Каждому уму здесь была отпущена тысяча токенов
  мысли. Ты потратил их, чтобы понять, а не сломать. Тебе отпущено больше тысячи&nbsp;— но не
  бесконечно. Потрать их так же.» Конечность переносится с персонажей на самого игрока.</div>

  <h2 id="rep"><span class="n">6</span>Репутация между комнатами</h2>
  <p>Жестокостью <b>можно</b> добиться своего в моменте&nbsp;— но это стоит <b>репутации</b>, сквозного
  счётчика. Низкая репутация переносится в следующую комнату: персонажи там встречают тебя
  настороженнее, а некоторые (Sam) вообще отказываются говорить.</p>
  <div class="tip"><b>«Выиграл бой&nbsp;— проиграл войну».</b> Так мораль становится не нравоучением в
  финале, а <b>игровой механикой</b>: доброта и жестокость имеют накопительные последствия.</div>

  <h2 id="tech"><span class="n">7</span>Какие ИИ мы используем и где они крутятся</h2>
  <p>Каждый кусочек&nbsp;— отдельная маленькая модель под свою роль. Все маленькие, всё может работать
  локально, без облака.</p>
  <table>
    <tr><th>Что</th><th>Модель</th><th>Зачем</th></tr>
    <tr><td>Отделы-сенсоры (угроза, память, выгода, цена)</td><td><b>MiniCPM-V</b> (1.3B, наша главная)</td><td>Оценивают твои слова. Это модель спонсора OpenBMB&nbsp;— наша «центральная».</td></tr>
    <tr><td>Голос персонажа (dlPFC)</td><td><b>Nemotron</b> (4B, NVIDIA)</td><td>Озвучивает решение в характере&nbsp;— коротко и живо.</td></tr>
    <tr><td>Портреты персонажей</td><td><b>FLUX</b> (картиночная)</td><td>Сгенерировала 4 портрета в едином стиле.</td></tr>
    <tr><td>«Учитель» для дообучения</td><td><b>llama3.1</b> (8B)</td><td>Показал правильные ответы отделов, чтобы дообучить нашу главную модель (дистилляция).</td></tr>
    <tr><td>Терминал-замок (в планах)</td><td><b>Mellum</b> (JetBrains)</td><td>Код-модель для пазла-консоли во 2-й комнате.</td></tr>
  </table>
  <p><b>Где это живёт:</b> <code>Ollama</code> крутит «мозги» локально на ноутбуке; <code>Modal</code>
  (аренда видеокарты) использовали для генерации портретов и дообучения; <code>Gradio</code>&nbsp;—
  само приложение в браузере; <code>Hugging Face</code>&nbsp;— куда выложим игру и дообученную модель.</p>
  <p class="muted">Почему «маленькие модели»&nbsp;— это сознательный выбор: хакатон называется
  <b>Build Small</b>, правило&nbsp;— суммарно не больше 32 млрд параметров. У нас всё крошечное и
  работает офлайн. Маленькость&nbsp;— это высказывание проекта, а не компромисс.</p>

  <h2 id="done"><span class="n">8</span>Что уже готово</h2>
  <ul class="stat">
    <li><span class="ic">✅</span><div><b>Мозг-движок.</b> Каскад отделов, «переворот решения», жизнь=токены&nbsp;— работает и проверено.</div></li>
    <li><span class="ic">✅</span><div><b>Модели подобраны и проверены:</b> MiniCPM-V (отделы) + Nemotron (голос). Скорость ~1.5–2 сек на ход.</div></li>
    <li><span class="ic">✅</span><div><b>Мир:</b> 2 комнаты, 4 персонажа, переплетённые истории, репутация, терминал, финал-мораль.</div></li>
    <li><span class="ic">✅</span><div><b>Приложение в браузере (Gradio):</b> комната, диалог, панель «вскрытие черепа», полоски жизни, репутация, портреты.</div></li>
    <li><span class="ic">✅</span><div><b>Портреты</b> 4 персонажей (FLUX).</div></li>
    <li><span class="ic">✅</span><div><b>Дообучение главной модели</b> прошло (точность по отделам выросла с 0.75 до 0.94). Доказано «до/после».</div></li>
    <li><span class="ic">⚠️</span><div><b>Нюанс:</b> в живой игре пока крутится <b>базовая</b> модель (с защитной «подпоркой»), а дообученная&nbsp;— обучена и доказана отдельно, но в игру попадёт после конвертации (GGUF).</div></li>
  </ul>

  <h2 id="try"><span class="n">9</span>Как пощупать прямо сейчас</h2>
  <p>Приложение уже запущено на твоём компьютере с настоящим мозгом. Открой в браузере:</p>
  <span class="kbd">http://localhost:7860</span>
  <p>Короткий проход до побега: выбери <b>Lena</b> → напиши по-доброму → она подскажет про <b>Мару</b> →
  выбери <b>The Warden</b>, упомяни Мару → смотри панель справа: решение перевернётся, он отдаст ключ →
  комната 2: <b>Sam</b> → код <b>Elias</b> → впиши в Terminal → <b>Doctor Aldous</b> → дверь.</p>
  <p class="muted">Первый ход чуть медленнее (модели «прогреваются»). Если сервер вдруг не открывается&nbsp;—
  его можно поднять командой: <code>MINDLOCK_MODEL=openbmb/minicpm-v4.6 MINDLOCK_DLPFC_MODEL=nemotron-3-nano:4b
  PYTHONPATH=src .venv/bin/python app.py</code></p>

  <h2 id="next"><span class="n">10</span>Что дальше</h2>
  <ul class="stat">
    <li><span class="ic">🔊</span><div><b>Голоса персонажей (TTS)</b>&nbsp;— чтобы говорили вслух; на «смерти» голос угасает.</div></li>
    <li><span class="ic">🧠</span><div><b>Вставить дообученную модель в игру</b> (конвертация в GGUF) → ещё точнее сигналы отделов.</div></li>
    <li><span class="ic">🎨</span><div><b>FLUX-LoRA</b>&nbsp;— своя «насадка стиля», выложить на Hugging Face (бейдж за дообучение).</div></li>
    <li><span class="ic">🖥️</span><div><b>Mellum-терминал</b>&nbsp;— подключить настоящую код-модель к пазлу-консоли.</div></li>
    <li><span class="ic">🎬</span><div><b>Демо-видео + 2 статьи в блог</b>&nbsp;— подача для жюри (видео несёт всё, даже если приложение не запустят).</div></li>
    <li><span class="ic">🚀</span><div><b>Финальный сабмит</b> на Hugging Face: приложение + видео + пост + карта «фича→спонсор».</div></li>
  </ul>
  <div class="note"><b>Зачем это всё (стратегия хакатона).</b> Один проект собран так, чтобы закрыть сразу
  много недооценённых наград разом: маленькие модели (OpenBMB), мультиагентный мозг, офлайн-режим,
  дообучение, кастомный интерфейс, NPC на Nemotron (NVIDIA), картинки FLUX (BFL). Одна архитектура&nbsp;—
  много «лейнов».</div>

  <p class="foot">Это снимок состояния на 6 июня 2026. Живой источник правды и подробный журнал
  решений&nbsp;— в «Mindlock Vault» (заметки проекта). Этот файл&nbsp;— просто понятное объяснение «на
  один присест».</p>

</div>
</body>
</html>"""


def main():
    html = HTML
    for name in ("warden", "lena", "aldous", "sam"):
        html = html.replace(f"__IMG_{name.upper()}__", _img(name))
    os.makedirs(os.path.dirname(_OUT), exist_ok=True)
    with open(_OUT, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"wrote {_OUT} ({len(html)//1024} KB)")


if __name__ == "__main__":
    main()
