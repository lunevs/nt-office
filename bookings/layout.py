"""Day layout: concurrent events share columns; crowded clusters become readable stacks.

Шкала всегда показывает рабочий день офиса 06:00–23:00 (макеты 01, 20, 23): свободные часы видны
и нажимаются — открывают бронь на это время, а при открытии шкала прокручивается к нужному часу."""

OPEN_MINUTE, CLOSE_MINUTE = 6 * 60, 23 * 60
DEFAULT_MINUTE = 9 * 60  # день без встреч открывается на 09:00
PIXELS_PER_MINUTE = 64 / 60  # свободный час — 64 px, как в макете 01


def minute(value):
    return value.hour * 60 + value.minute


def _clock(value):
    return f"{value // 60:02}:{value % 60:02}"


def day_layout(events, user=None, now_minute=None):
    """now_minute — текущая минута дня, если показываем сегодняшний день: даёт отметку «сейчас» на шкале."""
    start_minute = min([OPEN_MINUTE] + [minute(event.start_time) for event in events])
    end_minute = max([CLOSE_MINUTE] + [minute(event.end_time) for event in events])
    pixels_per_minute = PIXELS_PER_MINUTE
    groups = []
    for event in events:
        start, end = minute(event.start_time), minute(event.end_time)
        if not groups or start >= groups[-1]["end"]:
            groups.append({"start": start, "end": end, "events": []})
        group = groups[-1]
        group["end"] = max(end, group["end"])
        group["events"].append(event)
    for group in groups:
        lanes = []
        cards = []
        for event in group["events"]:
            start, end = minute(event.start_time), minute(event.end_time)
            lane = next((i for i, until in enumerate(lanes) if until <= start), len(lanes))
            if lane == len(lanes):
                lanes.append(end)
            else:
                lanes[lane] = end
            cards.append({"event": event, "lane": lane, "start": start, "end": end})
        group["cards"] = cards
        group["stacked"] = len(lanes) > 2
        group["columns"] = len(lanes)
        duration = group["end"] - group["start"]
        group["scale"] = max(pixels_per_minute, 116 * len(cards) / duration) if group["stacked"] else max(pixels_per_minute, max(116 / (c["end"] - c["start"]) for c in cards))

    def position(value):
        result = (value - start_minute) * pixels_per_minute
        for group in groups:
            consumed = max(0, min(value, group["end"]) - group["start"])
            result += consumed * (group["scale"] - pixels_per_minute)
        return round(result, 2)

    for group in groups:
        group["top"] = position(group["start"])
        group["height"] = round((group["end"] - group["start"]) * group["scale"], 2)
        for card in group["cards"]:
            card["top"] = round((card["start"] - group["start"]) * group["scale"], 2)
            card["height"] = round((card["end"] - card["start"]) * group["scale"], 2)
            card["left"] = card["lane"] * 100 / group["columns"]
            card["width"] = 100 / group["columns"]
    if user is not None:
        for group in groups:
            for card in group["cards"]:
                event = card["event"]
                room_ids = {room.pk for room in event.rooms.all()}
                conflict = any(other.pk != event.pk and other.start_time < event.end_time and other.end_time > event.start_time and room_ids.intersection(room.pk for room in other.rooms.all()) for other in events)
                card["event"] = event.visible_to(user, conflict)
            del group["events"]
    height = position(end_minute)
    markers = [value for value in range(-(-start_minute // 60) * 60, end_minute + 1, 60)]
    if markers[0] != start_minute:
        markers.insert(0, start_minute)
    if markers[-1] != end_minute:
        markers.append(end_minute)
    now_top = position(now_minute) if now_minute is not None and start_minute <= now_minute <= end_minute else None
    # Свободные часы: нажатие открывает бронь с этим временем. Сегодня прошедшие часы не предлагаем.
    slots = []
    for value in range(start_minute // 60 * 60, end_minute, 60):
        begin, finish = max(value, start_minute), min(value + 60, end_minute)
        if now_minute is not None and finish <= now_minute:
            continue
        slots.append({"start": _clock(begin), "top": position(begin), "height": round(position(finish) - position(begin), 2)})
    # Куда прокрутить шкалу: сегодня — к текущему часу, иначе — к первой встрече, в пустой день — к 09:00.
    target = now_minute if now_minute is not None else min((minute(event.start_time) for event in events), default=DEFAULT_MINUTE)
    # На телефоне нужный час — вверху (макет 01), на компьютере над ним видно ещё два часа (макет 23).
    hour = target // 60 * 60
    scroll_top = position(min(max(hour, start_minute), end_minute))
    scroll_top_wide = position(min(max(hour - 120, start_minute), end_minute))
    return {"groups": groups, "hours": [{"label": _clock(value), "top": position(value)} for value in markers], "height": height, "now_top": now_top, "slots": slots, "scroll_top": scroll_top, "scroll_top_wide": scroll_top_wide}
