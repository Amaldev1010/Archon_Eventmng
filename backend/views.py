
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import api_view, permission_classes
from django.contrib.auth import login
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model
from .models import Event, Registration
from .serializers import (
    EventSerializer,
    RegistrationSerializer,
    RegisterSerializer,
    LoginSerializer,
    UserSerializer,
)

User = get_user_model()

# ------------------- AUTH VIEWS ------------------------

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

class LoginView(APIView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            login(request, user)
            return Response(UserSerializer(user).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        return Response({"message": "Successfully logged out"}, status=200)

class UserDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        user = request.user
        username = user.username
        user.delete()
        return Response({"message": f"User '{username}' deleted successfully."}, status=200)

# ------------------- EVENT VIEWS ------------------------

class AddEventView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = EventSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(coordinator=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        events = Event.objects.filter(coordinator=request.user)
        serializer = EventSerializer(events, many=True)
        return Response(serializer.data)

class ListEventView(generics.ListAPIView):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    permission_classes = [IsAuthenticated]

class EditEventView(generics.RetrieveUpdateAPIView):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    permission_classes = [IsAuthenticated]

    def perform_update(self, serializer):
        if self.request.user != serializer.instance.coordinator:
            raise PermissionError("Only the event coordinator can update this event.")
        serializer.save()

class DeleteEventView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        try:
            event = Event.objects.get(pk=pk, coordinator=request.user)
            event.delete()
            return Response({'message': 'Event deleted'}, status=status.HTTP_204_NO_CONTENT)
        except Event.DoesNotExist:
            return Response({'error': 'Event not found or not authorized'}, status=status.HTTP_404_NOT_FOUND)

class MyEventsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        events = Event.objects.filter(coordinator=request.user)
        serializer = EventSerializer(events, many=True)
        return Response(serializer.data)

# ------------------- REGISTRATION VIEWS ------------------------

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def register_for_event(request, event_id):
    try:
        event = Event.objects.get(id=event_id)

        # ✅ Prevent duplicate registrations
        if Registration.objects.filter(user=request.user, event=event).exists():
            return Response({'message': 'You have already registered for this event.'}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Create the registration
        Registration.objects.create(user=request.user, event=event)

        # ✅ Send confirmation email to the participant's email
        send_mail(
            subject='Event Registration Successful',
            message=f'Hi {request.user.username}, you have successfully registered for the event "{event.title}".',
            from_email='amal007vadakkedath@gmail.com',
            recipient_list=[request.user.email],
            fail_silently=False,
        )

        return Response({'message': 'Registered successfully and confirmation email sent.'}, status=status.HTTP_201_CREATED)

    except Event.DoesNotExist:
        return Response({'error': 'Event not found.'}, status=status.HTTP_404_NOT_FOUND)


class CancelRegistrationView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, event_id):
        user = request.user
        try:
            event = Event.objects.get(pk=event_id)
            registration = Registration.objects.get(user=user, event=event)
            registration.delete()

            try:
                send_mail(
                    subject='Event Registration Cancelled',
                    message=f'Hi {user.username}, your registration for "{event.title}" has been cancelled.',
                    from_email='amal007vadakkedath@gmail.com',
                    recipient_list=[user.email],
                    fail_silently=False
                )
            except Exception as e:
                print(f"Email sending failed: {e}")

            return Response({'message': 'Registration cancelled successfully.'}, status=200)

        except Event.DoesNotExist:
            return Response({'error': 'Event not found.'}, status=404)
        except Registration.DoesNotExist:
            return Response({'error': 'You are not registered for this event.'}, status=400)

class EventParticipantsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, event_id):
        registrations = Registration.objects.filter(event__id=event_id)
        serializer = RegistrationSerializer(registrations, many=True)
        return Response(serializer.data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def registered_events(request):
    registrations = Registration.objects.filter(user=request.user)
    events = [reg.event for reg in registrations]
    serializer = EventSerializer(events, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_message_to_participants(request, event_id):
    message = request.data.get('message')
    if not message:
        return Response({'error': 'Message is required'}, status=400)

    try:
        event = Event.objects.get(id=event_id, coordinator=request.user)
    except Event.DoesNotExist:
        return Response({'error': 'Event not found or not authorized'}, status=404)

    registrations = Registration.objects.filter(event=event)
    emails = [reg.user.email for reg in registrations if reg.user.email]

    if not emails:
        return Response({'error': 'No participants found for this event'}, status=404)

    try:
        send_mail(
            subject=f'Message regarding event: {event.title}',
            message=f'Hi,\n\n{message}\n\nRegards,\n{request.user.username}',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=emails,
            fail_silently=False,
        )
        return Response({'success': f'Message sent to {len(emails)} participants'}, status=200)
    except Exception as e:
        return Response({'error': f'Failed to send email: {str(e)}'}, status=500)
