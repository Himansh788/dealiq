import { useState, useEffect } from 'react';

/**
 * Animates a number from 0 to target over duration using ease-out cubic easing.
 */
export function useCountUp(target: number, duration: number = 800) {
    const [count, setCount] = useState(0);

    useEffect(() => {
        let startTime: number | null = null;
        const endValue = target;
        const startValue = 0;

        const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);

        const animate = (currentTime: number) => {
            if (!startTime) startTime = currentTime;
            const elapsedTime = currentTime - startTime;
            const progress = Math.min(elapsedTime / duration, 1);

            const easedProgress = easeOutCubic(progress);

            setCount(Math.floor(startValue + (endValue - startValue) * easedProgress));

            if (progress < 1) {
                requestAnimationFrame(animate);
            } else {
                setCount(endValue);
            }
        };

        requestAnimationFrame(animate);
    }, [target, duration]);

    return count;
}
