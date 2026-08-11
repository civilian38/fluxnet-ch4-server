from rest_framework import permissions

class IsAdminUserOrReadOnly(permissions.BasePermission):
    """
    조회(GET)는 허용하되,
    생성/수정/삭제는 FCUser의 is_admin이 True인 경우만 허용하는 권한 클래스
    """

    def has_permission(self, request, view):
        # 1. 안전한 메서드(GET, HEAD, OPTIONS)는 통과 (조회 허용)
        if request.method in permissions.SAFE_METHODS:
            return True
            
        # 2. 그 외 쓰기/수정/삭제 요청은 로그인 상태이며, is_admin이 True일 때만 허용
        return bool(
            request.user and 
            request.user.is_authenticated and 
            getattr(request.user, 'is_admin', False)
        )