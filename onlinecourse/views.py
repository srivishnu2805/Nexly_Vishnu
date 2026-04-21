from django.shortcuts import render
from django.http import HttpResponseRedirect, HttpResponse, JsonResponse
from .models import Course, Enrollment, Question, Choice, Submission, ExamViolation, Lesson, Learner, UserLessonProgress
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from django.urls import reverse
from django.views import generic
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Max, Q, Sum
from django.core.paginator import Paginator
from django_ratelimit.decorators import ratelimit
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import CourseSerializer, LearnerSerializer, SubmissionSerializer
import logging
import json
import random
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)


# ─── Authentication ────────────────────────────────────────────────────────────

def registration_request(request):
    context = {}
    if request.method == 'GET':
        return render(request, 'onlinecourse/user_registration_bootstrap.html', context)
    elif request.method == 'POST':
        username = request.POST['username']
        password = request.POST['psw']
        first_name = request.POST['firstname']
        last_name = request.POST['lastname']
        user_exist = False
        try:
            User.objects.get(username=username)
            user_exist = True
        except:
            logger.error("New user")
        if not user_exist:
            user = User.objects.create_user(username=username, first_name=first_name, last_name=last_name,
                                            password=password)
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect("onlinecourse:index")
        else:
            context['message'] = "User already exists."
            return render(request, 'onlinecourse/user_registration_bootstrap.html', context)


@ratelimit(key='ip', rate='5/m', block=True)
def login_request(request):
    context = {}
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['psw']
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('onlinecourse:index')
        else:
            context['message'] = "Invalid username or password."
            return render(request, 'onlinecourse/user_login_bootstrap.html', context)
    else:
        return render(request, 'onlinecourse/user_login_bootstrap.html', context)


def logout_request(request):
    logout(request)
    return redirect('onlinecourse:index')


# ─── Helpers ───────────────────────────────────────────────────────────────────

def check_if_enrolled(user, course):
    is_enrolled = False
    if user.id is not None:
        num_results = Enrollment.objects.filter(user=user, course=course).count()
        if num_results > 0:
            is_enrolled = True
    return is_enrolled


def calculate_score(course, submission):
    """Calculate exam score for a submission."""
    total_score = 0
    questions = Question.objects.filter(course=course)
    for question in questions:
        selected_choices = submission.choices.filter(question=question)
        selected_ids = [c.id for c in selected_choices]
        if question.is_get_score(selected_ids):
            total_score += question.grade
    return total_score


# ─── Course List with Search & Pagination ──────────────────────────────────────

class CourseListView(generic.ListView):
    template_name = 'onlinecourse/course_list_bootstrap.html'
    context_object_name = 'course_list'
    paginate_by = 9

    def get_queryset(self):
        user = self.request.user
        query = self.request.GET.get('q', '')
        category = self.request.GET.get('category', '')
        difficulty = self.request.GET.get('difficulty', '')

        courses = Course.objects.all()
        
        # 🛡️ Filter out enrolled courses for the "Explore" page
        if user.is_authenticated:
            enrolled_course_ids = Enrollment.objects.filter(user=user).values_list('course_id', flat=True)
            courses = courses.exclude(id__in=enrolled_course_ids)

        if query:
            courses = courses.filter(
                Q(name__icontains=query) | Q(description__icontains=query)
            )
        if category:
            courses = courses.filter(category=category)
        if difficulty:
            courses = courses.filter(difficulty=difficulty)

        # Calculate student-driven average ratings
        for course in courses:
            rated_enrollments = Enrollment.objects.filter(course=course, is_rated=True)
            if rated_enrollments.exists():
                avg_rating = rated_enrollments.aggregate(Avg('rating'))['rating__avg']
                course.avg_rating = round(avg_rating, 1)
            else:
                course.avg_rating = 0.0

        courses = courses.order_by('-total_enrollment')
        return courses

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '')
        context['selected_category'] = self.request.GET.get('category', '')
        context['selected_difficulty'] = self.request.GET.get('difficulty', '')
        context['categories'] = Course.CATEGORY_CHOICES
        context['difficulties'] = Course.DIFFICULTY_CHOICES
        
        # 🌟 Daily Motivational Quote (Landing Page Only)
        if not self.request.user.is_authenticated:
            quotes = [
                "The only way to do great work is to love what you do. — Steve Jobs",
                "Success is not final, failure is not fatal: it is the courage to continue that counts. — Winston Churchill",
                "Believe you can and you're halfway there. — Theodore Roosevelt",
                "Your time is limited, don't waste it living someone else's life. — Steve Jobs",
                "The expert in anything was once a beginner. — Helen Hayes",
                "The mind is not a vessel to be filled, but a fire to be kindled. — Plutarch",
                "Innovation distinguishes between a leader and a follower. — Steve Jobs"
            ]
            import datetime
            day_of_year = datetime.datetime.now().timetuple().tm_yday
            context['motivational_quote'] = quotes[day_of_year % len(quotes)]
            
        return context


class EnrolledCourseListView(generic.ListView):
    template_name = 'onlinecourse/enrolled_courses.html'
    context_object_name = 'course_list'
    paginate_by = 9

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated:
            return Course.objects.filter(enrollment__user=user).order_by('-enrollment__date_enrolled')
        return Course.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # We can reuse the same filter categories if needed, but usually enrolled is simpler
        return context


class CourseDetailView(generic.DetailView):
    model = Course
    template_name = 'onlinecourse/course_detail_bootstrap.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        course = self.get_object()
        user = self.request.user

        # Randomize question order for each view
        questions = list(course.question_set.all())
        random.shuffle(questions)
        context['shuffled_questions'] = questions

        if user.is_authenticated:
            context['is_enrolled'] = check_if_enrolled(user, course)

            # Get completed lesson IDs
            completed_lesson_ids = list(UserLessonProgress.objects.filter(
                user=user, lesson__course=course
            ).values_list('lesson_id', flat=True))
            context['completed_lesson_ids'] = completed_lesson_ids

            # Calculate overall progress
            total_lessons = course.lesson_set.count()
            if total_lessons > 0:
                context['progress_percent'] = int((len(completed_lesson_ids) / total_lessons) * 100)
            else:
                context['progress_percent'] = 0

            # Get past attempts
            try:
                enrollment = Enrollment.objects.get(user=user, course=course)
                context['past_attempts'] = Submission.objects.filter(
                    enrollment=enrollment
                ).order_by('-timestamp')
            except Enrollment.DoesNotExist:
                context['past_attempts'] = []

        return context


@login_required(login_url='/onlinecourse/login/')
def take_exam(request, course_id):
    course = get_object_or_404(Course, pk=course_id)

    # 🛡️ Verify enrollment before allowing exam access
    if not check_if_enrolled(request.user, course):
        messages.error(request, "You must be enrolled in this course to take the final exam.")
        return redirect('onlinecourse:course_details', pk=course.id)

    # 🛡️ Server-Side Anti-Cheat: Set exam start time token ONLY when entering the exam page
    request.session[f'exam_start_{course.id}'] = datetime.now().timestamp()

    # Get shuffled questions
    questions = list(Question.objects.filter(course=course))
    random.shuffle(questions)

    context = {
        'course': course,
        'shuffled_questions': questions,
    }
    return render(request, 'onlinecourse/take_exam.html', context)



# ─── Enrollment ────────────────────────────────────────────────────────────────

def enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user = request.user

    is_enrolled = check_if_enrolled(user, course)
    if not is_enrolled and user.is_authenticated:
        Enrollment.objects.create(user=user, course=course, mode='honor')
        course.total_enrollment += 1
        course.save()

    return HttpResponseRedirect(reverse(viewname='onlinecourse:course_details', args=(course.id,)))


# ─── Exam Submission ──────────────────────────────────────────────────────────

@ratelimit(key='user', rate='2/m', block=True)
def submit(request, course_id):
    if not request.user.is_authenticated:
        return redirect('onlinecourse:login')

    course = get_object_or_404(Course, pk=course_id)
    enrollment = get_object_or_404(Enrollment, course=course, user=request.user)

    if request.method == 'POST':
        # 🛡️ Server-Side Anti-Cheat Validation
        if course.exam_time_limit > 0:
            start_time = request.session.get(f'exam_start_{course.id}')
            if start_time:
                elapsed_seconds = datetime.now().timestamp() - start_time
                max_allowed = (course.exam_time_limit * 60) + 120 # 2 minute buffer
                if elapsed_seconds > max_allowed:
                    messages.error(request, "Exam submission rejected: Time limit exceeded.")
                    ExamViolation.objects.create(
                        user=request.user, 
                        course=course, 
                        description=f"Server-side timeout violation ({int(elapsed_seconds)}s elapsed)"
                    )
                    return redirect('onlinecourse:course_details', pk=course.id)
            else:
                messages.error(request, "Exam submission rejected: Invalid session token.")
                return redirect('onlinecourse:course_details', pk=course.id)

        # Calculate attempt number
        previous_attempts = Submission.objects.filter(enrollment=enrollment).count()
        attempt_number = previous_attempts + 1

        # Get time taken from hidden field
        time_taken = int(request.POST.get('time_taken', 0))

        submission = Submission.objects.create(
            enrollment=enrollment,
            attempt_number=attempt_number,
            time_taken_seconds=time_taken
        )

        for key, value in request.POST.items():
            if key.startswith('choice_'):
                choice_id = int(value)
                choice = get_object_or_404(Choice, pk=choice_id)
                submission.choices.add(choice)

        # Calculate and save score
        score = calculate_score(course, submission)
        submission.score = score
        submission.passed = score >= course.passing_score
        submission.save()
        
        # 🚀 Tier 2: Trigger Async Task Engine (Certificate Dispatch)
        if submission.passed:
            from .tasks import generate_and_email_certificate
            generate_and_email_certificate.delay(submission.id)

        return redirect('onlinecourse:show_exam_result', course_id=course.id, submission_id=submission.id)


# ─── Exam Result ───────────────────────────────────────────────────────────────

def show_exam_result(request, course_id, submission_id):
    course = get_object_or_404(Course, pk=course_id)
    submission = get_object_or_404(Submission, pk=submission_id)

    # Check if this student has already rated this course
    is_rated = False
    if request.user.is_authenticated:
        enrollment = Enrollment.objects.filter(user=request.user, course=course).first()
        if enrollment:
            is_rated = enrollment.is_rated

    results = []
    questions = Question.objects.filter(course=course)
    for question in questions:
        selected_choices = submission.choices.filter(question=question)
        selected_ids = [c.id for c in selected_choices]
        is_correct = question.is_get_score(selected_ids)

        results.append({
            'question': question,
            'is_correct': is_correct,
            'selected_choices': selected_choices,
            'correct_choices': question.choice_set.filter(is_correct=True),
        })

    context = {
        'course': course,
        'submission': submission,
        'results': results,
        'total_score': submission.score,
        'passed': submission.passed,
        'is_rated': is_rated,
    }
    return render(request, 'onlinecourse/exam_result_bootstrap.html', context)


@login_required(login_url='/onlinecourse/login/')
def rate_course(request, course_id):
    if request.method == 'POST':
        course = get_object_or_404(Course, pk=course_id)
        enrollment = get_object_or_404(Enrollment, course=course, user=request.user)
        
        rating_val = request.POST.get('rating')
        if rating_val:
            enrollment.rating = float(rating_val)
            enrollment.is_rated = True
            enrollment.save()
            messages.success(request, "Thank you for your feedback! Your rating has been recorded.")
        
        return HttpResponseRedirect(reverse('onlinecourse:index'))
    return HttpResponseRedirect(reverse('onlinecourse:index'))


# ─── Exam Violation Logging ────────────────────────────────────────────────────

def log_violation(request, course_id):
    if request.method == 'POST' and request.user.is_authenticated:
        try:
            course = get_object_or_404(Course, pk=course_id)
            ExamViolation.objects.create(
                user=request.user,
                course=course,
                description="User minimized or exited full-screen during the exam."
            )
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'unauthorized'}, status=401)


# ─── Student Dashboard ────────────────────────────────────────────────────────

@login_required(login_url='/onlinecourse/login/')
def student_dashboard(request):
    user = request.user
    learner, _ = Learner.objects.get_or_create(user=user)
    enrollments = Enrollment.objects.filter(user=user).select_related('course')

    courses_data = []
    for enrollment in enrollments:
        submissions = Submission.objects.filter(enrollment=enrollment).order_by('-timestamp')
        best_score = submissions.aggregate(Max('score'))['score__max'] or 0
        latest = submissions.first()
        violations = ExamViolation.objects.filter(user=user, course=enrollment.course).count()

        # Calculate progress
        total_lessons = enrollment.course.lesson_set.count()
        completed_lessons = UserLessonProgress.objects.filter(
            user=user, lesson__course=enrollment.course
        ).count()
        progress_percent = int((completed_lessons / total_lessons * 100)) if total_lessons > 0 else 0

        courses_data.append({
            'course': enrollment.course,
            'enrollment': enrollment,
            'total_attempts': submissions.count(),
            'best_score': best_score,
            'latest_submission': latest,
            'passed': any(s.passed for s in submissions),
            'violations': violations,
            'progress_percent': progress_percent,
        })

    # Badge Logic
    badges = [
        {
            'id': 'explorer',
            'name': 'The Explorer',
            'icon': '🌍',
            'desc': 'Enrolled in 3+ courses',
            'unlocked': enrollments.count() >= 3
        },
        {
            'id': 'ace',
            'name': 'The Ace',
            'icon': '🎯',
            'desc': 'Scored 100% on any exam',
            'unlocked': Submission.objects.filter(enrollment__user=user, score=100).exists()
        },
        {
            'id': 'graduate',
            'name': 'The Graduate',
            'icon': '🎓',
            'desc': 'Passed your first course',
            'unlocked': any(c['passed'] for c in courses_data)
        }
    ]

    context = {
        'courses_data': courses_data,
        'total_courses': enrollments.count(),
        'total_passed': sum(1 for c in courses_data if c['passed']),
        'badges': badges,
        'learner': learner,
    }
    return render(request, 'onlinecourse/student_dashboard.html', context)


# ─── Leaderboard ───────────────────────────────────────────────────────────────

def leaderboard(request, course_id=None):
    if course_id:
        course = get_object_or_404(Course, pk=course_id)
        # Get best submission per student for this course
        submissions = Submission.objects.filter(
            enrollment__course=course
        ).values(
            'enrollment__user__username',
            'enrollment__user__first_name',
            'enrollment__user__last_name',
        ).annotate(
            best_score=Max('score'),
            total_attempts=Count('id'),
        ).order_by('-best_score')[:20]

        context = {
            'course': course,
            'rankings': submissions,
        }
    else:
        # 🛡️ Personal Leaderboard — Only show rankings for ENROLLED courses
        if request.user.is_authenticated:
            enrolled_courses = Course.objects.filter(enrollment__user=request.user)
        else:
            return redirect('onlinecourse:login')

        course_rankings = []
        for course in enrolled_courses:
            top_submissions = Submission.objects.filter(
                enrollment__course=course
            ).values(
                'enrollment__user__username',
                'enrollment__user__first_name',
            ).annotate(
                best_score=Max('score'),
            ).order_by('-best_score')[:5]

            if top_submissions:
                course_rankings.append({
                    'course': course,
                    'rankings': top_submissions,
                })

        context = {
            'course': None,
            'course_rankings': course_rankings,
        }

    return render(request, 'onlinecourse/leaderboard.html', context)


# ─── PDF Certificate Generation ───────────────────────────────────────────────

@login_required(login_url='/onlinecourse/login/')
def generate_certificate(request, course_id, submission_id):
    course = get_object_or_404(Course, pk=course_id)
    submission = get_object_or_404(Submission, pk=submission_id)

    # Verify ownership
    if submission.enrollment.user != request.user:
        return redirect('onlinecourse:index')

    # Must have passed
    if not submission.passed:
        return redirect('onlinecourse:show_exam_result', course_id=course.id, submission_id=submission.id)

    try:
        from reportlab.lib.pagesizes import landscape, A4
        from reportlab.lib.units import inch
        from reportlab.lib.colors import HexColor
        from reportlab.pdfgen import canvas

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="certificate_{course.name}_{request.user.username}.pdf"'

        c = canvas.Canvas(response, pagesize=landscape(A4))
        width, height = landscape(A4)

        # Background
        c.setFillColor(HexColor('#f8fafc'))
        c.rect(0, 0, width, height, fill=1)

        # Border
        c.setStrokeColor(HexColor('#6366f1'))
        c.setLineWidth(4)
        c.rect(30, 30, width - 60, height - 60)

        # Inner border
        c.setStrokeColor(HexColor('#a855f7'))
        c.setLineWidth(1)
        c.rect(40, 40, width - 80, height - 80)

        # Title
        c.setFillColor(HexColor('#6366f1'))
        c.setFont("Helvetica-Bold", 40)
        c.drawCentredString(width / 2, height - 120, "Certificate of Completion")

        # QR Code for Verification
        import qrcode
        from io import BytesIO
        from reportlab.lib.utils import ImageReader
        
        # Build absolute URL for verification
        verify_url = request.build_absolute_uri(
            reverse('onlinecourse:verify_certificate', args=[submission.verification_uuid])
        )
        
        qr = qrcode.QRCode(version=1, box_size=10, border=0)
        qr.add_data(verify_url)
        qr.make(fit=True)
        img_qr = qr.make_image(fill_color="#6366f1", back_color="#f8fafc")
        
        # Save QR to memory and draw
        qr_buffer = BytesIO()
        img_qr.save(qr_buffer, format='PNG')
        qr_buffer.seek(0)
        c.drawImage(ImageReader(qr_buffer), width - 140, 60, width=80, height=80)

        # Decorative line
        c.setStrokeColor(HexColor('#a855f7'))
        c.setLineWidth(2)
        c.line(width / 2 - 150, height - 135, width / 2 + 150, height - 135)

        # "This certifies that"
        c.setFillColor(HexColor('#64748b'))
        c.setFont("Helvetica", 16)
        c.drawCentredString(width / 2, height - 180, "This certifies that")

        # Student name
        c.setFillColor(HexColor('#1e293b'))
        c.setFont("Helvetica-Bold", 32)
        full_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
        c.drawCentredString(width / 2, height - 220, full_name)

        # Course completion text
        c.setFillColor(HexColor('#64748b'))
        c.setFont("Helvetica", 16)
        c.drawCentredString(width / 2, height - 265, "has successfully completed the course")

        # Course name
        c.setFillColor(HexColor('#6366f1'))
        c.setFont("Helvetica-Bold", 26)
        c.drawCentredString(width / 2, height - 305, course.name)

        # Score
        c.setFillColor(HexColor('#1e293b'))
        c.setFont("Helvetica", 14)
        c.drawCentredString(width / 2, height - 350, f"With a score of {submission.score}%")

        # Date
        from datetime import datetime
        date_str = submission.timestamp.strftime('%B %d, %Y') if submission.timestamp else datetime.now().strftime('%B %d, %Y')
        c.setFillColor(HexColor('#64748b'))
        c.setFont("Helvetica", 12)
        c.drawCentredString(width / 2, height - 390, f"Date: {date_str}")

        # Footer
        c.setFillColor(HexColor('#a855f7'))
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(width / 2, 80, "Nexly Learning Platform")

        c.setFillColor(HexColor('#64748b'))
        c.setFont("Helvetica", 10)
        c.drawCentredString(width / 2, 60, f"Certificate ID: EDUNEXT-{course.id}-{submission.id}-{request.user.id}")

        c.save()
        return response

    except ImportError:
        # Fallback: plain text certificate if reportlab is not installed
        response = HttpResponse(content_type='text/plain')
        response['Content-Disposition'] = f'attachment; filename="certificate_{course.name}_{request.user.username}.txt"'
        full_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
        content = f"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║              CERTIFICATE OF COMPLETION                       ║
║                                                              ║
║   This certifies that                                        ║
║                                                              ║
║   {full_name:^58s} ║
║                                                              ║
║   has successfully completed the course                      ║
║                                                              ║
║   {course.name:^58s} ║
║                                                              ║
║   Score: {submission.score}%                                  ║
║                                                              ║
║   Nexly Learning Platform                                  ║
║   Certificate ID: EDUNEXT-{course.id}-{submission.id}-{request.user.id}           ║
╚══════════════════════════════════════════════════════════════╝
"""
        response.write(content)
        return response


@login_required(login_url='/onlinecourse/login/')
def mark_lesson_complete(request, course_id, lesson_id):
    if request.method == 'POST':
        lesson = get_object_or_404(Lesson, pk=lesson_id)
        UserLessonProgress.objects.get_or_create(user=request.user, lesson=lesson)
        
        # ⚡ Update Streak Logic
        from datetime import date, timedelta
        learner, created = Learner.objects.get_or_create(user=request.user)
        today = date.today()
        
        if learner.last_activity_date == today:
            pass # Already updated today
        elif learner.last_activity_date == today - timedelta(days=1):
            learner.streak_count += 1
        else:
            learner.streak_count = 1
            
        learner.last_activity_date = today
        learner.save()
        
        return JsonResponse({'status': 'success', 'streak': learner.streak_count})
    return JsonResponse({'status': 'error'}, status=400)


# ─── Public Showcase Profile ────────────────────────────────────────

def public_showcase(request, username):
    target_user = get_object_or_404(User, username=username)
    learner = Learner.objects.filter(user=target_user).first()
    
    # Get all passed submissions
    passed_submissions = Submission.objects.filter(
        enrollment__user=target_user, passed=True
    ).select_related('enrollment__course')
    
    # Calculate Aggregate Skill DNA (Average across all courses)
    dna_metrics = [0, 0, 0, 0, 0] # Accuracy, Speed, Consistency, Focus, Mastery
    if passed_submissions.exists():
        total = passed_submissions.count()
        for sub in passed_submissions:
            # Re-using the logic for each submission to build aggregate
            accuracy = sub.score
            
            course = sub.enrollment.course
            if course.exam_time_limit > 0:
                speed = max(0, min(100, int((1 - (sub.time_taken_seconds / (course.exam_time_limit * 60))) * 100)))
            else:
                speed = 85
                
            prev_attempts = Submission.objects.filter(enrollment=sub.enrollment).count()
            consistency = max(0, 100 - (prev_attempts * 10))
            
            violations = ExamViolation.objects.filter(user=target_user, course=course).count()
            focus = max(0, 100 - (violations * 25))
            
            mastery = int((UserLessonProgress.objects.filter(user=target_user, lesson__course=course).count() / course.lesson_set.count() * 100)) if course.lesson_set.count() > 0 else 100
            
            dna_metrics[0] += accuracy
            dna_metrics[1] += speed
            dna_metrics[2] += consistency
            dna_metrics[3] += focus
            dna_metrics[4] += mastery
            
        dna_metrics = [int(m / total) for m in dna_metrics]

    context = {
        'target_user': target_user,
        'learner': learner,
        'submissions': passed_submissions,
        'dna_data': dna_metrics,
        'full_name': f"{target_user.first_name} {target_user.last_name}".strip() or target_user.username
    }
    return render(request, 'onlinecourse/public_showcase.html', context)


@login_required(login_url='/onlinecourse/login/')
def generate_study_guide(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user = request.user
    
    # Get all completed lessons for this course
    completed_progress = UserLessonProgress.objects.filter(
        user=user, lesson__course=course
    ).select_related('lesson').order_by('lesson__order')
    
    if not completed_progress.exists():
        return redirect('onlinecourse:course_details', pk=course.id)

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
        from reportlab.lib.units import inch
        from reportlab.lib.colors import HexColor

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Study_Guide_{course.name}.pdf"'

        doc = SimpleDocTemplate(response, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []

        # Custom Styles
        title_style = ParagraphStyle(
            'TitleStyle', parent=styles['Heading1'], fontSize=24, textColor=HexColor('#6366f1'),
            spaceAfter=20, alignment=1
        )
        lesson_style = ParagraphStyle(
            'LessonStyle', parent=styles['Heading2'], fontSize=18, textColor=HexColor('#1e293b'),
            spaceBefore=15, spaceAfter=10
        )
        content_style = ParagraphStyle(
            'ContentStyle', parent=styles['BodyText'], fontSize=11, leading=14, spaceAfter=12
        )

        # Header
        story.append(Paragraph(f"Smart Study Guide: {course.name}", title_style))
        story.append(Paragraph(f"Generated for: {user.first_name} {user.last_name}", styles['Normal']))
        story.append(Spacer(1, 0.5 * inch))

        for progress in completed_progress:
            lesson = progress.lesson
            story.append(Paragraph(f"Lesson: {lesson.title}", lesson_style))
            story.append(Spacer(1, 0.1 * inch))
            
            # Clean up content (handle newlines)
            content = lesson.content.replace('\n', '<br/>')
            story.append(Paragraph(content, content_style))
            story.append(Spacer(1, 0.3 * inch))

        story.append(PageBreak())
        doc.build(story)
        return response

    except ImportError:
        return HttpResponse("ReportLab not installed. Cannot generate PDF.", status=500)


# ─── Certificate Verification Page ───────────────────────────────────

def verify_certificate(request, verification_uuid):
    submission = get_object_or_404(Submission, verification_uuid=verification_uuid)
    course = submission.enrollment.course
    user = submission.enrollment.user
    
    # Calculate Skill DNA Metrics (0-100 scale)
    # 1. Accuracy (Final Score)
    accuracy = submission.score
    
    # 2. Speed (Lower time = Higher score)
    if course.exam_time_limit > 0:
        time_limit_secs = course.exam_time_limit * 60
        speed = max(0, min(100, int((1 - (submission.time_taken_seconds / time_limit_secs)) * 100)))
    else:
        speed = 85 # Default high speed if no limit
        
    # 3. Consistency (Based on previous attempts)
    prev_attempts = Submission.objects.filter(enrollment=submission.enrollment).count()
    consistency = max(0, 100 - (prev_attempts * 10)) # Fewer attempts = Higher consistency
    
    # 4. Focus (Violation check)
    violations = ExamViolation.objects.filter(user=user, course=course).count()
    focus = max(0, 100 - (violations * 25))
    
    # 5. Curriculum Mastery (Lesson completion)
    total_lessons = course.lesson_set.count()
    completed = UserLessonProgress.objects.filter(user=user, lesson__course=course).count()
    mastery = int((completed / total_lessons * 100)) if total_lessons > 0 else 100

    context = {
        'submission': submission,
        'course': course,
        'user': user,
        'full_name': f"{user.first_name} {user.last_name}".strip() or user.username,
        'date_completed': submission.timestamp.strftime('%B %d, %Y'),
        'dna_data': [accuracy, speed, consistency, focus, mastery]
    }
    return render(request, 'onlinecourse/verify_certificate.html', context)


# ─── Admin Analytics API (JSON for Chart.js) ──────────────────────────────────

@login_required(login_url='/onlinecourse/login/')
def admin_analytics(request):
    if not request.user.is_staff:
        return redirect('onlinecourse:index')

    courses = Course.objects.all()
    analytics_data = []

    for course in courses:
        submissions = Submission.objects.filter(enrollment__course=course)
        total_submissions = submissions.count()
        pass_count = submissions.filter(passed=True).count()
        fail_count = total_submissions - pass_count
        avg_score = submissions.aggregate(Avg('score'))['score__avg'] or 0
        violations = ExamViolation.objects.filter(course=course).count()

        analytics_data.append({
            'course_name': course.name,
            'total_submissions': total_submissions,
            'pass_count': pass_count,
            'fail_count': fail_count,
            'avg_score': round(avg_score, 1),
            'total_enrollment': course.total_enrollment,
            'violations': violations,
        })

    if request.GET.get('format') == 'json':
        return JsonResponse({'analytics': analytics_data})

    context = {
        'analytics_data': analytics_data,
        'analytics_json': json.dumps(analytics_data),
        'total_users': User.objects.count(),
        'total_courses': courses.count(),
        'total_submissions': Submission.objects.count(),
        'total_violations': ExamViolation.objects.count(),
    }
    return render(request, 'onlinecourse/admin_analytics.html', context)

# ─── Recruiter Portal (Two-Sided Marketplace) ────────────────────────────────

@login_required(login_url='/onlinecourse/login/')
def recruiter_portal(request):
    """
    Tier 3: A marketplace where recruiters can search for talent based on Skill DNA.
    """
    if not request.user.is_staff:
        # For demo purposes, we require staff/recruiter status.
        messages.error(request, "Access restricted to authorized recruiters only.")
        return redirect('onlinecourse:index')

    query = request.GET.get('skill', '')
    
    # Get all learners who have at least one passed course
    learners = Learner.objects.filter(
        user__enrollment__submission__passed=True
    ).distinct().select_related('user')
    
    talent_pool = []
    for learner in learners:
        user = learner.user
        passed_subs = Submission.objects.filter(enrollment__user=user, passed=True)
        
        if query:
            # Filter by specific course name
            passed_subs = passed_subs.filter(enrollment__course__name__icontains=query)
            if not passed_subs.exists():
                continue
                
        # Calculate DNA for the matched courses
        total = passed_subs.count()
        if total == 0:
            continue
            
        metrics = [0, 0, 0, 0, 0]
        for sub in passed_subs:
            course = sub.enrollment.course
            metrics[0] += sub.score
            metrics[1] += max(0, min(100, int((1 - (sub.time_taken_seconds / max(1, course.exam_time_limit * 60))) * 100))) if course.exam_time_limit > 0 else 85
            prev_attempts = Submission.objects.filter(enrollment=sub.enrollment).count()
            metrics[2] += max(0, 100 - (prev_attempts * 10))
            metrics[3] += max(0, 100 - (ExamViolation.objects.filter(user=user, course=course).count() * 25))
            completed = UserLessonProgress.objects.filter(user=user, lesson__course=course).count()
            total_l = course.lesson_set.count()
            metrics[4] += int((completed / total_l * 100)) if total_l > 0 else 100
            
        avg_metrics = [int(m / total) for m in metrics]
        overall_score = sum(avg_metrics) // 5
        
        talent_pool.append({
            'user': user,
            'learner': learner,
            'dna_metrics': avg_metrics,
            'overall_score': overall_score,
            'courses_passed': total,
        })
        
    # Sort by overall DNA score descending
    talent_pool.sort(key=lambda x: x['overall_score'], reverse=True)
    
    context = {
        'talent_pool': talent_pool,
        'search_query': query
    }
    return render(request, 'onlinecourse/recruiter_portal.html', context)


# ─── API Layer ──────────────────────────────────────────────────────────────

class CourseListAPI(APIView):
    """
    Returns a list of all available technical courses.
    """
    def get(self, request):
        courses = Course.objects.all().order_by('-total_enrollment')
        serializer = CourseSerializer(courses, many=True)
        return Response(serializer.data)


class PublicShowcaseAPI(APIView):
    """
    Returns a student's public profile data for external consumption.
    """
    def get(self, request, username):
        user = get_object_or_404(User, username=username)
        learner = get_object_or_404(Learner, user=user)
        passed_subs = Submission.objects.filter(enrollment__user=user, passed=True)
        
        return Response({
            'learner': LearnerSerializer(learner).data,
            'achievements': SubmissionSerializer(passed_subs, many=True).data
        })
