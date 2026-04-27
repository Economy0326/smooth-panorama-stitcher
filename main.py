import cv2
import numpy as np
import os
import glob


def load_images(folder_path):
    image_paths = sorted(glob.glob(os.path.join(folder_path, "*")))
    images = []

    for path in image_paths:
        img = cv2.imread(path)
        if img is not None:
            images.append(img)
            print(f"Loaded: {path}, shape={img.shape}")

    if len(images) < 3:
        raise ValueError("At least 3 images are required for this homework.")

    return images


def detect_and_match(img1, img2):
    gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

    orb = cv2.ORB_create(nfeatures=3000)

    kp1, des1 = orb.detectAndCompute(gray1, None)
    kp2, des2 = orb.detectAndCompute(gray2, None)

    if des1 is None or des2 is None:
        raise ValueError("Could not find enough features in one of the images.")

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)

    raw_matches = matcher.knnMatch(des1, des2, k=2)

    good_matches = []
    for m, n in raw_matches:
        if m.distance < 0.75 * n.distance:
            good_matches.append(m)

    print(f"Good matches: {len(good_matches)}")

    if len(good_matches) < 10:
        raise ValueError("Not enough good matches between images.")

    pts1 = np.float32([kp1[m.queryIdx].pt for m in good_matches])
    pts2 = np.float32([kp2[m.trainIdx].pt for m in good_matches])

    return pts1, pts2, kp1, kp2, good_matches


def compute_homography(img1, img2):
    pts1, pts2, kp1, kp2, matches = detect_and_match(img1, img2)

    # H maps img2 coordinate to img1 coordinate
    H, mask = cv2.findHomography(pts2, pts1, cv2.RANSAC, 5.0)

    if H is None:
        raise ValueError("Homography calculation failed.")

    inliers = int(mask.sum()) if mask is not None else 0
    print(f"Homography inliers: {inliers}/{len(matches)}")

    return H


def warp_two_images(base_img, next_img):
    h1, w1 = base_img.shape[:2]
    h2, w2 = next_img.shape[:2]

    H = compute_homography(base_img, next_img)

    corners_base = np.float32([
        [0, 0],
        [0, h1],
        [w1, h1],
        [w1, 0]
    ]).reshape(-1, 1, 2)

    corners_next = np.float32([
        [0, 0],
        [0, h2],
        [w2, h2],
        [w2, 0]
    ]).reshape(-1, 1, 2)

    warped_corners_next = cv2.perspectiveTransform(corners_next, H)

    all_corners = np.concatenate((corners_base, warped_corners_next), axis=0)

    x_min, y_min = np.int32(all_corners.min(axis=0).ravel() - 0.5)
    x_max, y_max = np.int32(all_corners.max(axis=0).ravel() + 0.5)

    translation_x = -x_min
    translation_y = -y_min

    translation_matrix = np.array([
        [1, 0, translation_x],
        [0, 1, translation_y],
        [0, 0, 1]
    ])

    canvas_width = x_max - x_min
    canvas_height = y_max - y_min

    warped_next = cv2.warpPerspective(
        next_img,
        translation_matrix @ H,
        (canvas_width, canvas_height)
    )

    warped_base = np.zeros((canvas_height, canvas_width, 3), dtype=np.uint8)
    warped_base[
        translation_y:translation_y + h1,
        translation_x:translation_x + w1
    ] = base_img

    blended = alpha_blend(warped_base, warped_next)

    return crop_black_area(blended)


def alpha_blend(img1, img2):
    mask1 = np.any(img1 > 0, axis=2).astype(np.float32)
    mask2 = np.any(img2 > 0, axis=2).astype(np.float32)

    overlap = (mask1 > 0) & (mask2 > 0)

    result = img1.copy().astype(np.float32)

    only_img2 = (mask1 == 0) & (mask2 > 0)
    result[only_img2] = img2[only_img2]

    # Simple average blending in overlapping area
    result[overlap] = 0.5 * img1[overlap].astype(np.float32) + 0.5 * img2[overlap].astype(np.float32)

    return np.clip(result, 0, 255).astype(np.uint8)


def crop_black_area(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return img

    largest_contour = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(largest_contour)

    cropped = img[y:y + h, x:x + w]
    return cropped


def stitch_images(images):
    panorama = images[0]

    for i in range(1, len(images)):
        print(f"\nStitching image {i + 1}/{len(images)}")
        panorama = warp_two_images(panorama, images[i])

    return panorama


def resize_for_display(img, max_width=1200):
    h, w = img.shape[:2]

    if w <= max_width:
        return img

    scale = max_width / w
    new_size = (int(w * scale), int(h * scale))
    return cv2.resize(img, new_size)


def main():
    input_folder = "images"
    output_folder = "results"
    output_path = os.path.join(output_folder, "panorama.jpg")

    os.makedirs(output_folder, exist_ok=True)

    images = load_images(input_folder)
    panorama = stitch_images(images)

    cv2.imwrite(output_path, panorama)
    print(f"\nSaved panorama to {output_path}")

    display = resize_for_display(panorama)
    cv2.imshow("Panorama Result", display)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()