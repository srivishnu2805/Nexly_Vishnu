from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from .models import Course, Lesson, Question, Choice, Enrollment, Submission, Learner, UserLessonProgress, ExamViolation
from .views import calculate_score
from datetime import date, datetime
from unittest.mock import patch

@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class NexlyModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.course = Course.objects.create(
            name="Test Course", 
            description="A test description",
            passing_score=80
        )
        self.question = Question.objects.create(course=self.course, question_text="What is 1+1?", grade=100)
        self.choice_correct = Choice.objects.create(question=self.question, choice_text="2", is_correct=True)
        self.choice_incorrect = Choice.objects.create(question=self.question, choice_text="3", is_correct=False)

    def test_question_score_correct(self):
        """Test that Question.is_get_score returns True for correct choices."""
        self.assertTrue(self.question.is_get_score([self.choice_correct.id]))

    def test_question_score_incorrect(self):
        """Test that Question.is_get_score returns False for incorrect choices."""
        self.assertFalse(self.question.is_get_score([self.choice_incorrect.id]))

    def test_question_score_partial(self):
        """Test that Question.is_get_score returns False if not all correct choices selected."""
        # Create another correct choice
        choice_correct2 = Choice.objects.create(question=self.question, choice_text="Two", is_correct=True)
        self.assertFalse(self.question.is_get_score([self.choice_correct.id]))
        self.assertTrue(self.question.is_get_score([self.choice_correct.id, choice_correct2.id]))

    def test_learner_streak_init(self):
        """Test Learner model streak initialization."""
        learner = Learner.objects.create(user=self.user)
        self.assertEqual(learner.streak_count, 0)
        self.assertIsNone(learner.last_activity_date)

@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class NexlyViewIntegrationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='student1', password='password123', first_name="Student")
        self.course = Course.objects.create(name="Python 101", description="Learn Python", passing_score=100)
        self.lesson = Lesson.objects.create(title="Intro", content="Hello world", course=self.course, order=1)
        self.question = Question.objects.create(course=self.course, question_text="Is Python fun?", grade=100)
        self.choice = Choice.objects.create(question=self.question, choice_text="Yes", is_correct=True)

    def test_index_view(self):
        response = self.client.get(reverse('onlinecourse:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Python 101")

    def test_course_detail_unauthenticated(self):
        response = self.client.get(reverse('onlinecourse:course_details', args=[self.course.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Login to Enroll")

    def test_enrollment_and_dashboard(self):
        self.client.login(username='student1', password='password123')
        # Enroll
        response = self.client.get(reverse('onlinecourse:enroll', args=[self.course.id]))
        self.assertEqual(response.status_code, 302) # Redirects to detail
        
        # Check Dashboard
        response = self.client.get(reverse('onlinecourse:student_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Python 101")

    def test_exam_submission_pass(self):
        self.client.login(username='student1', password='password123')
        self.client.get(reverse('onlinecourse:enroll', args=[self.course.id]))
        
        # Submit Exam
        submit_url = reverse('onlinecourse:submit', args=[self.course.id])
        data = {
            f'choice_{self.choice.id}': self.choice.id,
            'time_taken': 30
        }
        response = self.client.post(submit_url, data)
        self.assertEqual(response.status_code, 302) # Redirect to result
        
        # Check Submission record
        submission = Submission.objects.get(enrollment__user=self.user)
        self.assertTrue(submission.passed)
        self.assertEqual(submission.score, 100)

    def test_lesson_completion_and_streak(self):
        self.client.login(username='student1', password='password123')
        url = reverse('onlinecourse:mark_lesson_complete', args=[self.course.id, self.lesson.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        
        # Verify Progress
        self.assertTrue(UserLessonProgress.objects.filter(user=self.user, lesson=self.lesson).exists())
        
        # Verify Streak
        learner = Learner.objects.get(user=self.user)
        self.assertEqual(learner.streak_count, 1)
        self.assertEqual(learner.last_activity_date, date.today())

    def test_public_showcase(self):
        # Create a passed submission first
        enrollment = Enrollment.objects.create(user=self.user, course=self.course)
        submission = Submission.objects.create(enrollment=enrollment, score=100, passed=True)
        
        url = reverse('onlinecourse:public_showcase', args=[self.user.username])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Python 101")
        self.assertContains(response, "Skill DNA Profile")

    def test_certificate_verification(self):
        enrollment = Enrollment.objects.create(user=self.user, course=self.course)
        submission = Submission.objects.create(enrollment=enrollment, score=100, passed=True)
        
        url = reverse('onlinecourse:verify_certificate', args=[submission.verification_uuid])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Certificate Verified")
        self.assertContains(response, str(submission.verification_uuid))

@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class NexlySystemTests(TestCase):
    """System-level flow testing."""
    def test_complete_user_journey(self):
        c = Client()
        
        # 1. Registration
        reg_url = reverse('onlinecourse:registration')
        c.post(reg_url, {'username': 'newuser', 'psw': 'pass123', 'firstname': 'New', 'lastname': 'User'})
        user = User.objects.get(username='newuser')
        self.assertEqual(user.first_name, 'New')

        # 2. Course Discovery & Enrollment
        course = Course.objects.create(name="Deep Dive", passing_score=50)
        Lesson.objects.create(title="Lesson 1", content="Content", course=course)
        q = Question.objects.create(course=course, question_text="Q?", grade=100)
        Choice.objects.create(question=q, choice_text="Ans", is_correct=True)
        
        c.get(reverse('onlinecourse:enroll', args=[course.id]))
        
        # 3. Learning
        lesson = course.lesson_set.first()
        c.post(reverse('onlinecourse:mark_lesson_complete', args=[course.id, lesson.id]))
        
        # 4. Exam & Certification
        c.post(reverse('onlinecourse:submit', args=[course.id]), {
            f'choice_{q.choice_set.first().id}': q.choice_set.first().id,
            'time_taken': 10
        })
        
        submission = Submission.objects.get(enrollment__user=user)
        self.assertTrue(submission.passed)
        
        # 5. Verification
        verify_url = reverse('onlinecourse:verify_certificate', args=[submission.verification_uuid])
        response = c.get(verify_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New User")


@override_settings(STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class NexlyCoverageExpansionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='learner', password='pass123', first_name='Learn', last_name='Er')
        self.staff = User.objects.create_user(username='staffer', password='pass123', is_staff=True)
        self.course = Course.objects.create(
            name="Coverage Course",
            description="Coverage test course",
            passing_score=70,
            exam_time_limit=1,
        )
        self.lesson = Lesson.objects.create(title="L1", content="Lesson content", course=self.course, order=1)
        self.question = Question.objects.create(course=self.course, question_text="Pick correct", grade=100)
        self.correct_choice = Choice.objects.create(question=self.question, choice_text="Correct", is_correct=True)
        self.wrong_choice = Choice.objects.create(question=self.question, choice_text="Wrong", is_correct=False)
        self.enrollment = Enrollment.objects.create(user=self.user, course=self.course)

    def test_calculate_score_handles_mixed_answers(self):
        submission = Submission.objects.create(enrollment=self.enrollment)
        submission.choices.add(self.correct_choice)
        self.assertEqual(calculate_score(self.course, submission), 100)

        submission2 = Submission.objects.create(enrollment=self.enrollment)
        submission2.choices.add(self.wrong_choice)
        self.assertEqual(calculate_score(self.course, submission2), 0)

    def test_take_exam_redirects_when_not_enrolled(self):
        outsider = User.objects.create_user(username='outsider', password='pass123')
        self.client.login(username='outsider', password='pass123')
        response = self.client.get(reverse('onlinecourse:take_exam', args=[self.course.id]))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('onlinecourse:course_details', args=[self.course.id]))

    @patch('onlinecourse.tasks.generate_and_email_certificate.delay')
    def test_submit_rejects_time_limit_violation(self, mock_delay):
        self.client.login(username='learner', password='pass123')
        session = self.client.session
        session[f'exam_start_{self.course.id}'] = 0
        session.save()
        response = self.client.post(
            reverse('onlinecourse:submit', args=[self.course.id]),
            {f'choice_{self.correct_choice.id}': self.correct_choice.id, 'time_taken': 20},
        )
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('onlinecourse:course_details', args=[self.course.id]))
        self.assertEqual(Submission.objects.filter(enrollment=self.enrollment).count(), 0)
        self.assertEqual(ExamViolation.objects.filter(user=self.user, course=self.course).count(), 1)
        mock_delay.assert_not_called()

    def test_submit_rejects_missing_exam_session_token(self):
        self.client.login(username='learner', password='pass123')
        response = self.client.post(
            reverse('onlinecourse:submit', args=[self.course.id]),
            {f'choice_{self.correct_choice.id}': self.correct_choice.id, 'time_taken': 20},
        )
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('onlinecourse:course_details', args=[self.course.id]))
        self.assertEqual(Submission.objects.filter(enrollment=self.enrollment).count(), 0)

    @patch('onlinecourse.tasks.generate_and_email_certificate.delay')
    def test_submit_creates_attempt_and_queues_task_on_pass(self, mock_delay):
        self.client.login(username='learner', password='pass123')
        session = self.client.session
        session[f'exam_start_{self.course.id}'] = datetime.now().timestamp()
        session.save()
        response = self.client.post(
            reverse('onlinecourse:submit', args=[self.course.id]),
            {f'choice_{self.correct_choice.id}': self.correct_choice.id, 'time_taken': 25},
        )
        self.assertEqual(response.status_code, 302)
        submission = Submission.objects.get(enrollment=self.enrollment)
        self.assertEqual(submission.attempt_number, 1)
        self.assertTrue(submission.passed)
        mock_delay.assert_called_once_with(submission.id)

    def test_rate_course_updates_enrollment(self):
        self.client.login(username='learner', password='pass123')
        response = self.client.post(reverse('onlinecourse:rate_course', args=[self.course.id]), {'rating': '4.5'})
        self.assertEqual(response.status_code, 302)
        self.enrollment.refresh_from_db()
        self.assertTrue(self.enrollment.is_rated)
        self.assertEqual(self.enrollment.rating, 4.5)

    def test_log_violation_requires_authentication(self):
        response = self.client.post(reverse('onlinecourse:log_violation', args=[self.course.id]))
        self.assertEqual(response.status_code, 401)

    def test_log_violation_records_violation_for_authenticated_user(self):
        self.client.login(username='learner', password='pass123')
        response = self.client.post(reverse('onlinecourse:log_violation', args=[self.course.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ExamViolation.objects.filter(user=self.user, course=self.course).count(), 1)

    def test_admin_analytics_json_for_staff(self):
        Submission.objects.create(enrollment=self.enrollment, score=80, passed=True)
        self.client.login(username='staffer', password='pass123')
        response = self.client.get(reverse('onlinecourse:admin_analytics') + '?format=json')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload['analytics']), 1)
        self.assertEqual(payload['analytics'][0]['pass_count'], 1)

    def test_course_list_api_returns_courses(self):
        response = self.client.get(reverse('onlinecourse:api_course_list'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['name'], self.course.name)

    def test_public_showcase_api_returns_learner_profile(self):
        Learner.objects.create(user=self.user)
        Submission.objects.create(enrollment=self.enrollment, score=90, passed=True, time_taken_seconds=30)
        response = self.client.get(reverse('onlinecourse:api_public_showcase', args=[self.user.username]))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['learner']['username'], self.user.username)
        self.assertEqual(len(payload['achievements']), 1)
