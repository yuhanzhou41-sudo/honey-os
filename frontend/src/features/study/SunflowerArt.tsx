const STAGE_INDEX: Record<string, number> = { 种子: 0, 发芽: 1, 幼苗: 2, 长叶: 3, 花苞: 4 };

export function SunflowerArt({ stage, planted = false, size = 112, label }: {
  stage: string; planted?: boolean; size?: number; label?: string;
}) {
  const index = planted ? 5 : (STAGE_INDEX[stage] ?? 0);
  const aria = label ?? (planted ? "向日葵 · 已盛开" : stage);
  return (
    <svg viewBox="0 0 160 160" width={size} height={size} className="mx-auto" role="img" aria-label={aria}>
      <ellipse cx="80" cy="145" rx="46" ry="7" fill="#50684a" opacity=".12" />
      <path d="M51 107H109L102 141Q80 150 58 141Z" fill="#b37768" />
      <rect x="47" y="103" width="66" height="10" rx="4" fill="#d9b58c" />
      {index === 0 ? (
        <ellipse cx="80" cy="96" rx="7" ry="4" fill="#82634b" />
      ) : (
        <>
          <path d={`M80 105 Q76 86 80 ${index >= 3 ? 48 : 76}`} stroke="#5f8055" strokeWidth="5" fill="none" strokeLinecap="round" />
          <path d="M79 91Q49 93 49 70Q72 69 79 91" fill="#82a971" />
          <path d="M80 82Q109 83 110 59Q85 61 80 82" fill="#638c5d" />
          {index >= 3 && <path d="M79 66Q58 67 57 47Q75 47 79 66" fill="#a5bd87" />}
          {index === 4 && (
            <g>
              <ellipse cx="80" cy="43" rx="9" ry="13" fill="#7a9e5a" />
              <path d="M80 31 Q73 28 71 36 Q80 34 80 31 Z" fill="#9bbf73" />
              <path d="M80 31 Q87 28 89 36 Q80 34 80 31 Z" fill="#9bbf73" />
            </g>
          )}
          {index === 5 && (
            <g>
              {[0, 45, 90, 135, 180, 225, 270, 315].map(angle => (
                <ellipse key={angle} cx="80" cy="25" rx="7" ry="15" fill="#f2b705" transform={`rotate(${angle} 80 43)`} />
              ))}
              {[22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5].map(angle => (
                <ellipse key={angle} cx="80" cy="27" rx="5.5" ry="12" fill="#f59e0b" transform={`rotate(${angle} 80 43)`} />
              ))}
              <circle cx="80" cy="43" r="10" fill="#6b3410" />
              <circle cx="80" cy="43" r="10" fill="none" stroke="#3d1d08" strokeWidth="1" />
            </g>
          )}
        </>
      )}
    </svg>
  );
}
