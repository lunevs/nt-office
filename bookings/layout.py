"""Day layout: concurrent events share columns; crowded clusters become readable stacks."""

def minute(value):
    return value.hour * 60 + value.minute


def day_layout(events, user=None):
    if not events:
        return {"groups": [], "hours": [], "height": 0}
    start_minute = min(minute(event.start_time) for event in events)
    end_minute = max(minute(event.end_time) for event in events)
    pixels_per_minute = 0.6
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
    markers = [start_minute]
    for value in range((start_minute // 60 + 1) * 60, end_minute, 60):
        if position(value) - position(markers[-1]) >= 24 and height - position(value) >= 24:
            markers.append(value)
    markers.append(end_minute)
    return {"groups": groups, "hours": [{"label": f"{value // 60:02}:{value % 60:02}", "top": position(value)} for value in markers], "height": height}
