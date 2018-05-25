
from datetime import datetime, timedelta
from xml.etree.ElementTree import ParseError
import os.path
import json

# for Discourse SSO support
import base64
import hmac
import hashlib
import urllib
from urlparse import parse_qs
# SSO done

from django.contrib.auth import logout
from django.core.urlresolvers import reverse
from django.shortcuts import render
from django.shortcuts import redirect, get_object_or_404
from django.http import HttpResponseRedirect
from django.http import HttpResponseBadRequest
from django.http import Http404
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.template import RequestContext
from django.db.models import Q
from django.db.models import Count
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.utils.translation import ugettext as _
from django.utils.encoding import force_bytes
from django.views.decorators.cache import never_cache

from django.contrib.auth.models import User
from core.models import UserProfile
from core.forms import UserProfileForm
from core.forms import Wasa2ilRegistrationForm
from core.saml import authenticate, SamlException
from core.signals import user_verified
from core.utils import calculate_age_from_ssn
from core.utils import is_ssn_human_or_institution
from election.models import Election
from issue.forms import DocumentForm
from issue.models import Document
from issue.models import DocumentContent
from issue.models import Issue
from polity.models import Polity
from topic.models import Topic

from gateway.utils import update_member

from languagecontrol.utils import set_language

from hashlib import sha1

# BEGIN - Included for Wasa2ilLoginView
from django.contrib.auth import login as auth_login
from django.contrib.auth.views import LoginView
# END

# BEGIN - Included for Wasa2ilRegistrationView
from django.contrib.sites.shortcuts import get_current_site
from registration.backends.default.views import RegistrationView
from registration import signals as registration_signals
# END


def home(request):
    # Redirect to main polity, if it exists.
    try:
        polity = Polity.objects.get(is_front_polity=True)
        return HttpResponseRedirect(reverse('polity', args=(polity.id,)))
    except Polity.DoesNotExist:
        pass

    # If no polities have been created yet...
    if Polity.objects.count() == 0:
        # ...create one, if we have the access.
        if request.user.is_authenticated() and request.user.is_staff:
            return HttpResponseRedirect(reverse('polity_add'))

        # If we're logged out or don't have staff access, display welcome page.
        return render(request, 'welcome.html')

    else:
        # If polities exists, but there is no main polity, redirect to the
        # polity listing.
        return HttpResponseRedirect(reverse('polities'))


def help(request, page):
    ctx = {
        'language_code': settings.LANGUAGE_CODE
    }
    for locale in [settings.LANGUAGE_CODE, "is"]: # Icelandic fallback
      filename = "help/%s/%s.html" % (locale, page)
      if os.path.isfile(os.path.join(os.path.dirname(__file__), '..', 'wasa2il/templates', filename)):
          return render(request, filename, ctx)

    raise Http404


@never_cache
@login_required
def profile(request, username=None):
    ctx = {}

    # Determine if we're looking up the currently logged in user or someone else.
    if username:
        profile_user = get_object_or_404(User, username=username)
    elif request.user.is_authenticated():
        profile_user = request.user
    else:
        return HttpResponseRedirect(settings.LOGIN_URL)

    polities = profile_user.polities.all()
    profile = UserProfile.objects.get(user_id=profile_user.id)

    # Get running elections in which the user is currently a candidate
    now = datetime.now()
    elections = Election.objects.filter(candidate__user=profile_user)
    current_elections = elections.filter(deadline_votes__gte=now)

    ctx = {
        'polities': polities,
        'current_elections': current_elections,
        'elections': elections,
        'profile_user': profile_user,
        'profile': profile,
    }
    return render(request, 'profile/profile.html', ctx)


@never_cache
def user_proposals(request, username=None):
    ctx = {}

    # Determine if we're looking up the currently logged in user or someone else.
    if username:
        profile_user = get_object_or_404(User, username=username)
    elif request.user.is_authenticated():
        profile_user = request.user
    else:
        return HttpResponseRedirect(settings.LOGIN_URL)

    polities = profile_user.polities.all()
    profile = UserProfile.objects.get(user_id=profile_user.id)

    # # Get documents and documentcontents which user has made
    # documentdata = []
    # contents = profile_user.documentcontent_set.select_related('document').order_by('document__name', 'order')
    # last_doc_id = 0
    # for c in contents:
    #     if c.document_id != last_doc_id:
    #         documentdata.append(c.document) # Template will detect the type as Document and show as heading
    #         last_doc_id = c.document_id
    #
    #     documentdata.append(c)

    # Get running elections in which the user is currently a candidate
    now = datetime.now()
    current_elections = Election.objects.filter(candidate__user=profile_user, deadline_votes__gte=now)

    ctx = {
        'polities': polities,
        # 'documentdata': documentdata,
        'profile_user': profile_user,
        'profile': profile,
    }
    return render(request, 'profile/proposals.html', ctx)



@login_required
def view_settings(request):
    ctx = {}
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request=request, instance=UserProfile.objects.get(user=request.user))
        if form.is_valid():
            # FIXME/TODO: When a user changes email addresses, there is
            # currently no functionality to verify the new email address.
            # Therefore, the email field is disabled in UserProfileForm until
            # that functionality has been implemented.
            #request.user.email = form.cleaned_data['email']
            #request.user.save()
            form.save()

            set_language(request, form.cleaned_data['language'])

            if 'picture' in request.FILES:
                f = request.FILES.get("picture")
                m = sha1()
                m.update(force_bytes(request.user.username))
                hash = m.hexdigest()
                ext = f.name.split(".")[1] # UserProfileForm.clean_picture() makes sure this is safe.
                filename = "userimg_%s.%s" % (hash, ext)
                path = settings.MEDIA_ROOT + "/" + filename
                #url = settings.MEDIA_URL + filename
                pic = open(path, 'wb+')
                for chunk in f.chunks():
                    pic.write(chunk)
                pic.close()
                p = request.user.userprofile
                p.picture.name = filename
                p.save()

            if hasattr(settings, 'ICEPIRATE'):
                # The request.user object doesn't yet reflect recently made
                # changes, so we need to ask the database explicitly.
                update_member(User.objects.get(id=request.user.id))

            return HttpResponseRedirect("/accounts/profile/")
        else:
            print "FAIL!"
            ctx["form"] = form
            return render(request, "settings.html", ctx)

    else:
        form = UserProfileForm(initial={'email': request.user.email}, instance=UserProfile.objects.get(user=request.user))

    ctx["form"] = form
    return render(request, "settings.html", ctx)


class Wasa2ilRegistrationView(RegistrationView):

    form_class = Wasa2ilRegistrationForm

    def register(self, form):

        site = get_current_site(self.request)

        new_user_instance = form.save()

        userprofile = new_user_instance.userprofile
        userprofile.email_wanted = form['email_wanted'].value() == 'True'
        userprofile.save()

        new_user = self.registration_profile.objects.create_inactive_user(
            new_user=new_user_instance,
            site=site,
            send_email=self.SEND_ACTIVATION_EMAIL,
            request=self.request,
        )

        registration_signals.user_registered.send(
            sender=self.__class__,
            user=new_user,
            request=self.request
        )

        return new_user


@login_required
def verify(request):

    try:
        auth = authenticate(request, settings.SAML_1['URL'])
    except SamlException as e:
        ctx = {'e': e}
        return render(request, 'registration/saml_error.html', ctx)
    except ParseError:
        logout(request)
        return redirect(reverse('auth_login'))

    # Make sure that the user is, in fact, human.
    if is_ssn_human_or_institution(auth['ssn']) != 'human':
        ctx = {
            'ssn': auth['ssn'],
            'name': auth['name'].encode('utf8'),
        }
        return render(request, 'registration/verification_invalid_entity.html', ctx)


    # Make sure that user has reached the minimum required age, if applicable.
    if hasattr(settings, 'AGE_LIMIT') and settings.AGE_LIMIT > 0:
        age = calculate_age_from_ssn(auth['ssn'])
        if age < settings.AGE_LIMIT:
            logout(request)
            ctx = {
                'age': age,
                'age_limit': settings.AGE_LIMIT,
            }
            return render(request, 'registration/verification_age_limit.html', ctx)

    if UserProfile.objects.filter(verified_ssn=auth['ssn']).exists():
        taken_user = UserProfile.objects.select_related('user').get(verified_ssn=auth['ssn']).user
        ctx = {
            'auth': auth,
            'taken_user': taken_user,
        }

        logout(request)

        return render(request, 'registration/verification_duplicate.html', ctx)

    profile = request.user.userprofile  # It shall exist at this point
    profile.verified_ssn = auth['ssn']
    profile.verified_name = auth['name'].encode('utf8')
    profile.verified_token = request.GET['token']
    profile.verified_timing = datetime.now()
    profile.save()

    user_verified.send(sender=request.user.__class__, user=request.user, request=request)

    return HttpResponseRedirect('/')


@login_required
def login_or_saml_redirect(request):
    '''
    Check if user is verified. If so, redirect to the specified login
    redirection page. Otherwise, redirect to the SAML login page for
    verification. This is done in a view instead of redirecting straight from
    SamlMiddleware so that other login-related middleware can be allowed to do
    their thing before the SAML page, most notably TermsAndConditions, which
    we want immediately following the login, before verification.
    '''
    if request.user.userprofile.verified:
        return settings.LOGIN_REDIRECT_URL
    else:
        return redirect(settings.SAML_1['URL'])


@login_required
def sso(request):
    if not hasattr(settings, 'DISCOURSE'):
        raise Http404

    key = str(settings.DISCOURSE['secret'])
    return_url = '%s/session/sso_login' % settings.DISCOURSE['url']

    payload = request.GET.get('sso')
    their_signature = request.GET.get('sig')

    if None in [payload, their_signature]:
        return HttpResponseBadRequest('Required parameters missing.')

    try:
        payload = urllib.unquote(payload)
        decoded = base64.decodestring(payload)
        assert 'nonce' in decoded
        assert len(payload) > 0
    except:
        return HttpResponseBadRequest('Malformed payload.')

    our_signature = hmac.new(key, payload, digestmod=hashlib.sha256).hexdigest()

    if our_signature != their_signature:
        return HttpResponseBadRequest('Malformed payload.')

    nonce = parse_qs(decoded)['nonce'][0]
    outbound = {
        'nonce': nonce,
        'email': request.user.email,
        'external_id': request.user.id,
        'username': request.user.username,
    }

    out_payload = base64.encodestring(urllib.urlencode(outbound))
    out_signature = hmac.new(key, out_payload, digestmod=hashlib.sha256).hexdigest()
    out_query = urllib.urlencode({'sso': out_payload, 'sig' : out_signature})

    return HttpResponseRedirect('%s?%s' % (return_url, out_query))


def error500(request):
    return render(request, '500.html')
