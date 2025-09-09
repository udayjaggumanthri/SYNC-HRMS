from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import QueryDict, JsonResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from base.models import Company
from facedetection.forms import FaceDetectionSetupForm
from horilla.decorators import hx_request_required

from .serializers import *


class FaceDetectionConfigAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_company(self, request):
        try:
            company = request.user.employee_get.get_company()
            return company
        except Exception as e:
            raise serializers.ValidationError(e)

    def get_facedetection(self, request):
        company = self.get_company(request)
        try:
            facedetection = FaceDetection.objects.get(company_id=company)
            return facedetection
        except Exception as e:
            raise serializers.ValidationError(e)

    def get(self, request):
        serializer = FaceDetectionSerializer(self.get_facedetection(request))
        return Response(serializer.data, status=status.HTTP_200_OK)

    @method_decorator(
        permission_required("facedetection.add_facedetection", raise_exception=True),
        name="dispatch",
    )
    def post(self, request):
        data = request.data
        if isinstance(data, QueryDict):
            data = data.dict()
        data["company_id"] = self.get_company(request).id
        serializer = FaceDetectionSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @method_decorator(
        permission_required("facedetection.change_facedetection", raise_exception=True),
        name="dispatch",
    )
    def put(self, request):
        data = request.data
        if isinstance(data, QueryDict):
            data = data.dict()
        data["company_id"] = self.get_company(request).id
        serializer = FaceDetectionSerializer(self.get_facedetection(request), data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @method_decorator(
        permission_required("facedetection.delete_facedetection", raise_exception=True),
        name="dispatch",
    )
    def delete(self, request):
        self.get_facedetection(request).delete()
        return Response(
            {"message": "Facedetection deleted successfully"}, status=status.HTTP_200_OK
        )


class EmployeeFaceDetectionGetPostAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_company(self, request):
        try:
            company = request.user.employee_get.get_company()
            return company
        except Exception as e:
            raise serializers.ValidationError(e)

    def get_facedetection(self, request):
        company = self.get_company(request)
        try:
            facedetection = FaceDetection.objects.get(company_id=company)
            return facedetection
        except Exception as e:
            raise serializers.ValidationError(e)

    def post(self, request):
        if self.get_facedetection(request).start:
            employee_id = request.user.employee_get.id
            data = request.data
            if isinstance(data, QueryDict):
                data = data.dict()
            data["employee_id"] = employee_id
            serializer = EmployeeFaceDetectionSerializer(data=data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        raise serializers.ValidationError("Facedetection not yet started..")


def get_company(request):
    try:
        selected_company = request.session.get("selected_company")
        if selected_company == "all":
            return None
        company = Company.objects.get(id=selected_company)
        return company
    except Exception as e:
        raise serializers.ValidationError(e)


def get_facedetection(request):
    company = get_company(request)
    try:
        location = FaceDetection.objects.get(company_id=company)
        return location
    except Exception as e:
        raise serializers.ValidationError(e)


@login_required
@permission_required("geofencing.add_localbackup")
@hx_request_required
def face_detection_config(request):
    try:
        form = FaceDetectionSetupForm(instance=get_facedetection(request))
    except:
        form = FaceDetectionSetupForm()

    if request.method == "POST":
        try:
            form = FaceDetectionSetupForm(
                request.POST, instance=get_facedetection(request)
            )
        except:
            form = FaceDetectionSetupForm(request.POST)
        if form.is_valid():
            facedetection = form.save(
                commit=False,
            )
            facedetection.company_id = get_company(request)
            facedetection.save()
            messages.success(request, _("facedetection config created successfully."))
        else:
            messages.info(request, "Not valid")
    return render(request, "face_config.html", {"form": form})


@login_required
@csrf_exempt
def employee_face_registration(request):
    """
    Handle employee face image upload for attendance tracking
    """
    if request.method == 'POST':
        try:
            # Check if face detection is enabled for the company
            company = request.user.employee_get.get_company()
            try:
                face_detection = FaceDetection.objects.get(company_id=company)
                if not face_detection.start:
                    return JsonResponse({
                        'success': False,
                        'message': _('Face detection is not enabled for your company. Please contact your administrator.')
                    })
            except FaceDetection.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': _('Face detection is not configured for your company. Please contact your administrator.')
                })
            
            # Get or create employee face detection record
            employee = request.user.employee_get
            face_image = request.FILES.get('image')
            
            if not face_image:
                return JsonResponse({
                    'success': False,
                    'message': _('Please select an image file.')
                })
            
            # Validate file type
            allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif']
            if face_image.content_type not in allowed_types:
                return JsonResponse({
                    'success': False,
                    'message': _('Please upload a valid image file (JPG, PNG, or GIF).')
                })
            
            # Validate file size (5MB limit)
            if face_image.size > 5 * 1024 * 1024:
                return JsonResponse({
                    'success': False,
                    'message': _('File size too large. Please upload an image smaller than 5MB.')
                })
            
            # Validate that the image contains a detectable face
            from .face_recognition_utils import validate_face_image
            import tempfile
            
            try:
                # Create temporary file to validate the image
                with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
                    for chunk in face_image.chunks():
                        temp_file.write(chunk)
                    temp_file_path = temp_file.name
                
                # Validate the face image
                validation_result = validate_face_image(temp_file_path)
                
                # Clean up temporary file
                os.unlink(temp_file_path)
                
                if not validation_result['valid']:
                    return JsonResponse({
                        'success': False,
                        'message': _(validation_result['message'])
                    })
                    
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': _('Error validating face image. Please try again.')
                })
            
            # Create or update employee face detection
            employee_face_detection, created = EmployeeFaceDetection.objects.get_or_create(
                employee_id=employee,
                defaults={'image': face_image}
            )
            
            if not created:
                # Update existing record
                employee_face_detection.image = face_image
                employee_face_detection.save()
            
            return JsonResponse({
                'success': True,
                'message': _('Face image uploaded successfully! You can now use face recognition for attendance tracking.'),
                'face_image_url': employee_face_detection.image.url
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': _('An error occurred while uploading the face image. Please try again.')
            })
    
    return JsonResponse({
        'success': False,
        'message': _('Invalid request method.')
    })


@login_required
@require_http_methods(["DELETE"])
@csrf_exempt
def employee_face_delete(request):
    """
    Handle employee face image deletion
    """
    try:
        employee = request.user.employee_get
        try:
            employee_face_detection = EmployeeFaceDetection.objects.get(employee_id=employee)
            employee_face_detection.delete()
            return JsonResponse({
                'success': True,
                'message': _('Face image deleted successfully.')
            })
        except EmployeeFaceDetection.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': _('No face image found to delete.')
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': _('An error occurred while deleting the face image. Please try again.')
        })


@login_required
def employee_profile_with_face(request):
    """
    Enhanced employee profile view that includes face detection data
    """
    try:
        employee = request.user.employee_get
        face_detection = None
        try:
            face_detection = EmployeeFaceDetection.objects.get(employee_id=employee)
        except EmployeeFaceDetection.DoesNotExist:
            pass
        
        # Get the original employee profile view context
        from employee.views import self_info_update
        # This would need to be modified to include face_detection in context
        # For now, we'll return the face detection data separately
        
        return JsonResponse({
            'face_detection': {
                'has_image': face_detection is not None,
                'image_url': face_detection.image.url if face_detection else None
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': _('An error occurred while loading profile data.')
        })


@login_required
def face_attendance_interface(request):
    """
    Display the face recognition attendance interface
    """
    try:
        # Check if face detection is enabled for the company
        company = request.user.employee_get.get_company()
        try:
            face_detection = FaceDetection.objects.get(company_id=company)
            if not face_detection.start:
                return render(request, 'facedetection/face_attendance_disabled.html', {
                    'message': _('Face detection is not enabled for your company. Please contact your administrator.')
                })
        except FaceDetection.DoesNotExist:
            return render(request, 'facedetection/face_attendance_disabled.html', {
                'message': _('Face detection is not configured for your company. Please contact your administrator.')
            })
        
        # Check if employee has registered their face
        employee = request.user.employee_get
        try:
            employee_face = EmployeeFaceDetection.objects.get(employee_id=employee)
        except EmployeeFaceDetection.DoesNotExist:
            return render(request, 'facedetection/face_attendance_not_registered.html', {
                'message': _('Please register your face image first in your profile before using face recognition attendance.')
            })
        
        return render(request, 'facedetection/face_attendance_interface.html', {
            'employee_face': employee_face,
            'employee': employee
        })
        
    except Exception as e:
        return render(request, 'facedetection/face_attendance_error.html', {
            'message': _('An error occurred while loading the face recognition interface.')
        })


@login_required
@csrf_exempt
def face_attendance_clock_in(request):
    """
    Handle face recognition clock in
    """
    if request.method == 'POST':
        try:
            # Check if face detection is enabled
            company = request.user.employee_get.get_company()
            try:
                face_detection = FaceDetection.objects.get(company_id=company)
                if not face_detection.start:
                    return JsonResponse({
                        'success': False,
                        'message': _('Face detection is not enabled for your company.')
                    })
            except FaceDetection.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': _('Face detection is not configured for your company.')
                })
            
            # Get employee face data
            employee = request.user.employee_get
            try:
                employee_face = EmployeeFaceDetection.objects.get(employee_id=employee)
            except EmployeeFaceDetection.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': _('Please register your face image first.')
                })
            
            # Perform actual face recognition
            captured_image = request.FILES.get('captured_image')
            if not captured_image:
                return JsonResponse({
                    'success': False,
                    'message': _('No image captured. Please try again.')
                })
            
            # Use face recognition to compare captured image with stored face
            from .face_recognition_utils import compare_uploaded_face_with_stored
            
            try:
                # Get the path to the stored face image
                stored_face_path = employee_face.image.path
                
                # Compare faces with a tolerance of 0.6 (adjustable)
                recognition_result = compare_uploaded_face_with_stored(
                    stored_face_path, 
                    captured_image, 
                    tolerance=0.6
                )
                
                recognition_success = recognition_result.get('face_matched', False)
                recognition_message = recognition_result.get('message', 'Face recognition completed')
                
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': _('Error during face recognition. Please try again.')
                })
            
            if recognition_success:
                # Call the existing clock in function
                from attendance.views.clock_in_out import clock_in
                response = clock_in(request)
                
                if response.status_code == 200:
                    return JsonResponse({
                        'success': True,
                        'message': _('Face recognition successful! Clocked in successfully.'),
                        'html': response.content.decode('utf-8')
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'message': _('Clock in failed. Please try again.')
                    })
            else:
                return JsonResponse({
                    'success': False,
                    'message': _('Face recognition failed. Please ensure your face is clearly visible and try again.')
                })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': _('An error occurred during face recognition. Please try again.')
            })
    
    return JsonResponse({
        'success': False,
        'message': _('Invalid request method.')
    })


@login_required
@csrf_exempt
def face_attendance_clock_out(request):
    """
    Handle face recognition clock out
    """
    if request.method == 'POST':
        try:
            # Check if face detection is enabled
            company = request.user.employee_get.get_company()
            try:
                face_detection = FaceDetection.objects.get(company_id=company)
                if not face_detection.start:
                    return JsonResponse({
                        'success': False,
                        'message': _('Face detection is not enabled for your company.')
                    })
            except FaceDetection.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': _('Face detection is not configured for your company.')
                })
            
            # Get employee face data
            employee = request.user.employee_get
            try:
                employee_face = EmployeeFaceDetection.objects.get(employee_id=employee)
            except EmployeeFaceDetection.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'message': _('Please register your face image first.')
                })
            
            # Perform actual face recognition
            captured_image = request.FILES.get('captured_image')
            if not captured_image:
                return JsonResponse({
                    'success': False,
                    'message': _('No image captured. Please try again.')
                })
            
            # Use face recognition to compare captured image with stored face
            from .face_recognition_utils import compare_uploaded_face_with_stored
            
            try:
                # Get the path to the stored face image
                stored_face_path = employee_face.image.path
                
                # Compare faces with a tolerance of 0.6 (adjustable)
                recognition_result = compare_uploaded_face_with_stored(
                    stored_face_path, 
                    captured_image, 
                    tolerance=0.6
                )
                
                recognition_success = recognition_result.get('face_matched', False)
                recognition_message = recognition_result.get('message', 'Face recognition completed')
                
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': _('Error during face recognition. Please try again.')
                })
            
            if recognition_success:
                # Call the existing clock out function
                from attendance.views.clock_in_out import clock_out
                response = clock_out(request)
                
                if response.status_code == 200:
                    return JsonResponse({
                        'success': True,
                        'message': _('Face recognition successful! Clocked out successfully.'),
                        'html': response.content.decode('utf-8')
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'message': _('Clock out failed. Please try again.')
                    })
            else:
                return JsonResponse({
                    'success': False,
                    'message': _('Face recognition failed. Please ensure your face is clearly visible and try again.')
                })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': _('An error occurred during face recognition. Please try again.')
            })
    
    return JsonResponse({
        'success': False,
        'message': _('Invalid request method.')
    })
