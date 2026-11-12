from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count, Max
from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from .forms import MessageForm
from .models import Message

User = get_user_model()

def pair_messages(user, person):
    return Message.objects.filter(Q(sender=user, recipient=person) | Q(sender=person, recipient=user))

def participant(request, pk):
    if pk == request.user.pk:
        raise Http404
    return get_object_or_404(User, pk=pk, is_active=True)

def positive_id(value, default=0):
    try:
        result = int(value)
        return result if 0 < result <= 9223372036854775807 else default
    except (TypeError, ValueError):
        return default

@login_required
@never_cache
@require_GET
def inbox(request):
    sent = Message.objects.filter(sender=request.user).values('recipient').annotate(last_id=Max('id'))
    received = Message.objects.filter(recipient=request.user).values('sender').annotate(last_id=Max('id'))
    latest = {}
    for row in sent:
        latest[row['recipient']] = row['last_id']
    for row in received:
        latest[row['sender']] = max(latest.get(row['sender'], 0), row['last_id'])
    unread = dict(Message.objects.filter(recipient=request.user, read_at__isnull=True).values('sender').annotate(total=Count('pk')).values_list('sender', 'total'))
    messages = Message.objects.filter(pk__in=latest.values()).select_related('sender', 'recipient').order_by('-pk')
    conversations = []
    for message in messages:
        person = message.recipient if message.sender_id == request.user.pk else message.sender
        if person.is_active:
            conversations.append({'person': person, 'last': message, 'unread': unread.get(person.pk, 0)})
    return render(request, 'messaging/inbox.html', {'conversations': conversations})

@login_required
@never_cache
@require_GET
def people(request):
    query = request.GET.get('q', '').strip()[:150]
    users = User.objects.filter(is_active=True).exclude(pk=request.user.pk)
    if query:
        users = users.filter(Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(username__icontains=query))
    from django.core.paginator import Paginator
    page = Paginator(users.order_by('last_name', 'first_name', 'username'), 30).get_page(request.GET.get('page'))
    return render(request, 'messaging/people.html', {'people': page, 'query': query})

@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def thread(request, pk):
    person = participant(request, pk)
    form = MessageForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        Message.objects.create(sender=request.user, recipient=person, text=form.cleaned_data['text'])
        return redirect('message_thread', pk=person.pk)
    before = positive_id(request.GET.get('before'))
    queryset = pair_messages(request.user, person)
    if before:
        queryset = queryset.filter(pk__lt=before)
    recent = list(queryset.order_by('-pk')[:51])
    has_older = len(recent) > 50
    items = list(reversed(recent[:50]))
    return render(request, 'messaging/thread.html', {'person': person, 'form': form, 'items': items, 'has_older': has_older, 'older_cursor': items[0].pk if items else 0, 'cursor': items[-1].pk if items else 0, 'history': bool(before)})

@login_required
@never_cache
@require_GET
def updates(request, pk):
    person = participant(request, pk)
    after = positive_id(request.GET.get('after'))
    items = pair_messages(request.user, person).filter(pk__gt=after).order_by('pk')[:100]
    return JsonResponse({'messages': [{'id': item.pk, 'text': item.text, 'own': item.sender_id == request.user.pk, 'time': timezone.localtime(item.created_at).strftime('%d.%m.%Y %H:%M')} for item in items]})

@login_required
@never_cache
@require_POST
def mark_read(request, pk):
    person = participant(request, pk)
    through = positive_id(request.POST.get('through'))
    Message.objects.filter(sender=person, recipient=request.user, pk__lte=through, read_at__isnull=True).update(read_at=timezone.now())
    return JsonResponse({'unread': request.user.received_messages.filter(read_at__isnull=True).count()})
