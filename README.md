# browser

## 이벤트 책임 분리 구조
```
Tkinter
  ↓
Browser (수신 + 분기)
  ↓
Chrome (주소창, 탭, UI 의미)
  ↓
Tab (링크 클릭, 입력, 제출 등)
```

## 각 객체별 역할

- Browser: 운영체제 이벤트 처리
- Chrome: 브라우저 UI 의미 부여
- Tab: 문서/페이지 로직