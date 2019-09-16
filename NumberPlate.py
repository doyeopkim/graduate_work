import cv2
import numpy as np
import pytesseract
import time
from PIL import Image

# --Read Input Image-- (이미지 불러오기)

src = cv2.imread("987987987.jpg", cv2.IMREAD_COLOR) # 이미지 불러오기

'''
dst = src.copy()           #이미지영역을 반으로 자르기(번호판 인식률 속도를 높이기 위함)
dst = src[480:960, 50:670]

cv2.imshow("half img", dst)
cv2.waitKey(0)
'''

prevtime = time.time() # 걸린 시간 체크하는 함수

# 변수 선언
height, width, channel = src.shape # 이미지에 대한 값을 가질 변수

numcheck = 0 # 반복문에서 번호판 문자열 검사할 변수
charsok = 0 # 반복문에서 번호판 글자를 제대로 읽었는지 검사할 변수
add_w_padding, add_h_padding = 0, 0 # 추가할 padding값을 가질 변수
w_padding_max, h_padding_max = 0, 0 # 일정한 padding값을 가지게되었을때 반복문을 제어할 변수

# --Convert Image to Grayscale-- (이미지 흑백변환)

gray = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY) # 이미지 흑백변환

# --Maximize Contrast(Optional)-- (흑백대비 최대화)

structuringElement = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))

imgTopHat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, structuringElement)
imgBlackHat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, structuringElement)

imgGrayscalePlusTopHat = cv2.add(gray, imgTopHat)
gray = cv2.subtract(imgGrayscalePlusTopHat, imgBlackHat)

# --Adaptive Thresholding-- (가우시안블러(이미지 노이즈 제거) 및 쓰레시 홀딩)

img_blurred = cv2.GaussianBlur(gray, ksize=(5, 5), sigmaX=0) # GaussianBlur 적용

img_thresh = cv2.adaptiveThreshold( # adaptiveThreshold 적용
    img_blurred,
    maxValue=255.0,
    adaptiveMethod=cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
    thresholdType=cv2.THRESH_BINARY_INV,
    blockSize=19,
    C=9
)

# --Find Contours-- (윤곽선 찾기)

contours, hierarchy = cv2.findContours( # opencv의 findContours를 이용하여 contours에 저장
    img_thresh,
    cv2.RETR_LIST,
    cv2.CHAIN_APPROX_SIMPLE
)

temp_result = np.zeros((height, width, channel), dtype=np.uint8) # numpy.zeros를 이용하여 윤곽선 범위 저장

cv2.drawContours(temp_result, contours, -1, (255, 255, 255)) # 윤곽선 그리기


# --Prepare Data-- (데이터 비교하기, 글자영역으로 추정되는 rectangle 그리기)

temp_result = np.zeros((height, width, channel), dtype=np.uint8) # drawContours를 이용해 그린 윤곽선에 다시 numpy.zeros를 이용해 다시 윤곽선 범위 저장 (안하면 윤곽선 좀 남아있음)


contours_dict = [] # contour 정보를 모두 저장받을 리스트 변수

for contour in contours:
    x, y, w, h = cv2.boundingRect(contour) # 위치 높낮이 데이터 정보 저장
    cv2.rectangle(temp_result, pt1=(x, y), pt2=(x + w, y + h), color=(255, 255, 255), thickness=2) # 윤곽선을 감싸는 사각형 구하기

    # insert to dict
    contours_dict.append({ # contour 정보를 모두 저장
        'contour': contour,
        'x': x,
        'y': y,
        'w': w,
        'h': h,
        'cx': x + (w / 2),
        'cy': y + (h / 2)
    })

# --Select Candidates by Char Size-- (글자 같은 영역 찾기)

MIN_AREA = 80 # 윤곽선의 가운데 렉트 최소 넓이 80
MIN_WIDTH, MIN_HEIGHT = 2, 8 # 바운드 렉트의 최소 너비와 높이는 2, 8
MIN_RATIO, MAX_RATIO = 0.25, 1.0 # 바운드 렉트의 비율 가로 대비 세로 비율 최솟값 0.25, 최댓값 1.0

possible_contours = [] # 글자로 예상되는 contour들을 저장받을 리스트 변수

cnt = 0 # count 변수
for d in contours_dict: # contours_dict에 저장된 것을 조건에 맞다면 possible_contours에 append
    area = d['w'] * d['h']
    ratio = d['w'] / d['h']

    if area > MIN_AREA \
            and d['w'] > MIN_WIDTH and d['h'] > MIN_HEIGHT \
            and MIN_RATIO < ratio < MAX_RATIO:
        d['idx'] = cnt
        cnt += 1
        possible_contours.append(d)

# visualize possible contours
temp_result = np.zeros((height, width, channel), dtype=np.uint8)

for d in possible_contours:
    #     cv2.drawContours(temp_result, d['contour'], -1, (255, 255, 255))
    cv2.rectangle(temp_result, pt1=(d['x'], d['y']), pt2=(d['x'] + d['w'], d['y'] + d['h']), color=(255, 255, 255),
                  thickness=2) # 글자로 예상되는 영역만 rectangle 그리기

# --Select Candidates by Arrangement of Contours-- (글자의 연속성(번호판으로 예상되는 영역) 찾기)

MAX_DIAG_MULTIPLYER = 4.7  # 5 contour와 contour의 사이의 길이 (값계속 바꿔가면서 테스트 해야함)
MAX_ANGLE_DIFF = 13  # 12.0 첫번째 contour와 두번째 contour의 직각 삼각형의 앵글 세타각도
MAX_AREA_DIFF = 0.5  # 0.5  면적의 차이
MAX_WIDTH_DIFF = 0.8 # 0.8 contour 간의 가로길이 차이
MAX_HEIGHT_DIFF = 0.2 # 0.2 contour 간의 세로길이 차이
MIN_N_MATCHED = 4  # 3 글자영역으로 예측된 것의 최소 갯수 (ex 3개이상이면 번호판일 것)


def find_chars(contour_list):
    matched_result_idx = []

    for d1 in contour_list:
        matched_contours_idx = []
        for d2 in contour_list:
            if d1['idx'] == d2['idx']:
                continue

            dx = abs(d1['cx'] - d2['cx'])
            dy = abs(d1['cy'] - d2['cy'])

            diagonal_length1 = np.sqrt(d1['w'] ** 2 + d1['h'] ** 2)

            distance = np.linalg.norm(np.array([d1['cx'], d1['cy']]) - np.array([d2['cx'], d2['cy']]))
            if dx == 0:
                angle_diff = 90
            else:
                angle_diff = np.degrees(np.arctan(dy / dx))
            area_diff = abs(d1['w'] * d1['h'] - d2['w'] * d2['h']) / (d1['w'] * d1['h'])
            width_diff = abs(d1['w'] - d2['w']) / d1['w']
            height_diff = abs(d1['h'] - d2['h']) / d1['h']

            if distance < diagonal_length1 * MAX_DIAG_MULTIPLYER \
                    and angle_diff < MAX_ANGLE_DIFF and area_diff < MAX_AREA_DIFF \
                    and width_diff < MAX_WIDTH_DIFF and height_diff < MAX_HEIGHT_DIFF:
                matched_contours_idx.append(d2['idx'])

        # append this contour
        matched_contours_idx.append(d1['idx'])

        if len(matched_contours_idx) < MIN_N_MATCHED:
            continue

        matched_result_idx.append(matched_contours_idx)

        unmatched_contour_idx = []
        for d4 in contour_list:
            if d4['idx'] not in matched_contours_idx:
                unmatched_contour_idx.append(d4['idx'])

        unmatched_contour = np.take(possible_contours, unmatched_contour_idx)

        # recursive
        recursive_contour_list = find_chars(unmatched_contour)

        for idx in recursive_contour_list:
            matched_result_idx.append(idx)

        break

    return matched_result_idx


result_idx = find_chars(possible_contours)

matched_result = []
for idx_list in result_idx:
    matched_result.append(np.take(possible_contours, idx_list))

# visualize possible contours
temp_result = np.zeros((height, width, channel), dtype=np.uint8)

for r in matched_result:
    for d in r:
        #         cv2.drawContours(temp_result, d['contour'], -1, (255, 255, 255))
        cv2.rectangle(temp_result, pt1=(d['x'], d['y']), pt2=(d['x'] + d['w'], d['y'] + d['h']), color=(255, 255, 255),
                      thickness=2)

cv2.imwrite('07.jpg', temp_result) #글자영역 추출

# --Rotate Plate Images--

plate_imgs = []
plate_infos = []

longest_idx, longest_text = -1, 0
plate_chars = []

while charsok == 0:
    print("와일문이 돌았다")
    PLATE_WIDTH_PADDING = 1.267 + add_w_padding  # 1.3 #1.265
    print("가로 패딩값")
    print(PLATE_WIDTH_PADDING)
    PLATE_HEIGHT_PADDING = 1.51 + add_h_padding  # 1.5 #1.55
    print("세로 패딩값")
    print(PLATE_HEIGHT_PADDING)
    MIN_PLATE_RATIO = 3 #3
    MAX_PLATE_RATIO = 10 #10

    for i, matched_chars in enumerate(matched_result):
        sorted_chars = sorted(matched_chars, key=lambda x: x['cx'])

        plate_cx = (sorted_chars[0]['cx'] + sorted_chars[-1]['cx']) / 2
        plate_cy = (sorted_chars[0]['cy'] + sorted_chars[-1]['cy']) / 2

        plate_width = (sorted_chars[-1]['x'] + sorted_chars[-1]['w'] - sorted_chars[0]['x']) * PLATE_WIDTH_PADDING

        sum_height = 0
        for d in sorted_chars:
            sum_height += d['h']

        plate_height = int(sum_height / len(sorted_chars) * PLATE_HEIGHT_PADDING)

        triangle_height = sorted_chars[-1]['cy'] - sorted_chars[0]['cy']
        triangle_hypotenus = np.linalg.norm(
            np.array([sorted_chars[0]['cx'], sorted_chars[0]['cy']]) -
            np.array([sorted_chars[-1]['cx'], sorted_chars[-1]['cy']])
        )

        angle = np.degrees(np.arcsin(triangle_height / triangle_hypotenus))

        rotation_matrix = cv2.getRotationMatrix2D(center=(plate_cx, plate_cy), angle=angle, scale=1.0)

        img_rotated = cv2.warpAffine(img_thresh, M=rotation_matrix, dsize=(width, height))

        img_cropped = cv2.getRectSubPix(
            img_rotated,
            patchSize=(int(plate_width), int(plate_height)),
            center=(int(plate_cx), int(plate_cy))
        )

        if img_cropped.shape[1] / img_cropped.shape[0] < MIN_PLATE_RATIO or img_cropped.shape[1] / img_cropped.shape[
            0] < MIN_PLATE_RATIO > MAX_PLATE_RATIO:
            continue

        plate_imgs.append(img_cropped)

        plate_infos.append({
            'x': int(plate_cx - plate_width / 2),
            'y': int(plate_cy - plate_height / 2),
            'w': int(plate_width),
            'h': int(plate_height)
        })

    cv2.imwrite('08.jpg', img_cropped) #사진 돌려서 각도 맞추기(Rotate)

    # --Another Thresholding to Find Chars--

    for i, plate_img in enumerate(plate_imgs):
        if numcheck > 3: # 예상되는 번호판 영역에서 문자열을 검사해 숫자 3개가 넘는다면(번호판일 확률이 높다면)
            break # for문을 멈춤

        plate_img = cv2.resize(plate_img, dsize=(0, 0), fx=1.6, fy=1.6)
        _, plate_img = cv2.threshold(plate_img, thresh=0.0, maxval=255.0, type=cv2.THRESH_BINARY | cv2.THRESH_OTSU)

        # find contours again (same as above)
        contours, hierarchy = cv2.findContours(plate_img, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

        plate_min_x, plate_min_y = plate_img.shape[1], plate_img.shape[0]
        plate_max_x, plate_max_y = 0, 0

        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)

            area = w * h
            ratio = w / h

            if area > MIN_AREA \
                    and w > MIN_WIDTH and h > MIN_HEIGHT \
                    and MIN_RATIO < ratio < MAX_RATIO:
                if x < plate_min_x:
                    plate_min_x = x
                if y < plate_min_y:
                    plate_min_y = y
                if x + w > plate_max_x:
                    plate_max_x = x + w
                if y + h > plate_max_y:
                    plate_max_y = y + h

        img_result = plate_img[plate_min_y:plate_max_y, plate_min_x:plate_max_x]

        img_result = cv2.GaussianBlur(img_result, ksize=(3, 3), sigmaX=0) #최종값 굵기조정
        _, img_result = cv2.threshold(img_result, thresh=0.0, maxval=255.0, type=cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        img_result = cv2.copyMakeBorder(img_result, top=10, bottom=10, left=10, right=10, borderType=cv2.BORDER_CONSTANT,
                                        value=(0, 0, 0))

        cv2.imwrite('00.jpg', img_result)
        chars = pytesseract.image_to_string(Image.open('00.jpg'), config='--psm 7 --oem 0', lang='kor')
        nowtime = time.time()
        sec = nowtime - prevtime
        print("걸린시간 %0.5f" % sec)
        print("이미지 불러 온 후 글자 : " + chars)

        result_chars = ''
        has_digit = False
        for c in chars:
            if ord('가') <= ord(c) <= ord('힣') or c.isdigit():
                if c.isdigit():
                    has_digit = True
                result_chars += c
        nowtime = time.time()
        sec = nowtime - prevtime
        print("result_chars : " + result_chars)
        plate_chars.append(result_chars)

        for j in range(len(result_chars)):
            if len(result_chars) < 7:
                break
            if (j == 2 and result_chars[j].isdigit() == True) or (j == 3 and result_chars[j].isdigit() == True):
                break
            if (j != 2 or j != 3) and result_chars[j].isdigit() == False:
                break
            if (j == 2 and result_chars[j].isdigit() == False) and (j == 3 and result_chars[j].isdigit() == False):
                break
            if 6 <= j <= 8 and result_chars[j].isdigit() == True:
                charsok = 1

        if has_digit and len(result_chars) > longest_text:
            longest_idx = i

        for numch, in chars:
            if numch.isdigit() == True:
                numcheck += 1

    cv2.imwrite('09.jpg', img_result)

    # --Result--

    info = plate_infos[longest_idx]
    chars = plate_chars[longest_idx]

    for n in range(len(chars)):
        if len(chars) < 7:
            print("번호판 인식 오류")
            break
        elif chars[0].isdigit() == False:
            print("첫문자 오류 : " + chars)
            chars = chars[1:chars.__len__()]
        elif chars[len(chars)-1].isdigit() == False:
            print("마지막문자 오류 : " + chars)
            chars = chars[0:(chars.__len__()-1)]

    print("걸린시간 %0.1f" %sec)
    img_out = src.copy()

    for j in range(len(chars)):
        if len(chars) < 7:
            plate_imgs = []
            plate_chars = []
            break
        if (j == 2 and chars[j].isdigit() == True) and (j == 3 and chars[j].isdigit() == True):
            plate_imgs = []
            plate_chars = []
            break
        if (j != 2 and chars[j].isdigit() == False) and (j != 3 and chars[j].isdigit() == False):
            plate_imgs = []
            plate_chars = []
            break
        if 6 <= j <= 8 and chars[j].isdigit() == True:
            charsok = 1
    numcheck = 0

    if add_w_padding <= 0.6 and w_padding_max == 0:     # w패딩이 0.5보다 작다면
        add_w_padding += 0.1    # w패딩을 0.1씩 증가

    elif w_padding_max == 1 and add_h_padding <= 0.6 and h_padding_max == 0:    # w패딩이 0.5를 찍고 h패딩이 0.5보다 작다면
        add_w_padding = 0      # w패딩을 다시 Default값으로
        add_h_padding += 0.1    # h패딩을 0.1씩 증가

    if add_w_padding == 0.6:
        w_padding_max = 1
    if add_h_padding == 0.6:
        h_padding_max = 1
        add_w_padding = 0
        add_h_padding = 0

    if w_padding_max == 1 and h_padding_max == 1:
        add_w_padding += 0.1
        add_h_padding += 0.1
        if add_w_padding == 0.6 and add_h_padding == 0.6:
            break

print("최종 값 : " + chars)

cv2.rectangle(img_out, pt1=(info['x'], info['y']), pt2=(info['x'] + info['w'], info['y'] + info['h']),
              color=(255, 0, 0), thickness=2)

cv2.imwrite('010.jpg', img_out) #원본 이미지에서 번호판 영역 추출한 사진
cv2.imshow('result', img_out)
cv2.waitKey(0)