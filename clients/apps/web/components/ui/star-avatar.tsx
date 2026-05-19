'use client';

import { cn } from '@/lib/utils';

interface StarAvatarProps {
  size?: number;
  className?: string;
}

export function StarAvatar({ size = 28, className }: StarAvatarProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 28 28"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn('shrink-0', className)}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="starGradient" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse">
          <stop stopColor="#FF8C42" />
          <stop offset="1" stopColor="#FFB888" />
        </linearGradient>
      </defs>
      <path
        d="M14 2L16.5 11.5H26L18.5 17L21 26L14 21L7 26L9.5 17L2 11.5H11.5L14 2Z"
        fill="url(#starGradient)"
      />
    </svg>
  );
}
