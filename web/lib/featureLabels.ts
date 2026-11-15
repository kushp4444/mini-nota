const plainNames: Record<string, string> = {
  "firstorder_10Percentile": "Low CT intensity (10th percentile)",
  "firstorder_90Percentile": "High CT intensity (90th percentile)",
  firstorder_Mean: "Average CT intensity",
  firstorder_Median: "Middle CT intensity",
  firstorder_Minimum: "Lowest CT intensity",
  firstorder_Maximum: "Highest CT intensity",
  firstorder_Range: "Difference between highest and lowest intensity",
  firstorder_InterquartileRange: "Spread of the middle half of CT intensities",
  firstorder_Entropy: "Variety of CT intensities (entropy)",
  firstorder_Uniformity: "How concentrated the CT intensities are",
  shape_VoxelVolume: "Tumor volume from the mask (mm³)",
  shape_MeshVolume: "Tumor volume from the surface outline (mm³)",
  shape_SurfaceArea: "Tumor surface area (mm²)",
  shape_SurfaceVolumeRatio: "Tumor surface area relative to volume",
  shape_Sphericity: "How close the tumor shape is to a sphere",
  shape_Elongation: "How stretched out the tumor shape is",
  shape_Flatness: "How flat the tumor shape is",
  shape_Maximum3DDiameter: "Widest distance across the tumor (mm)",
  glcm_Contrast: "Contrast between neighboring points",
  glcm_Correlation: "How closely neighboring intensities vary together",
  glcm_JointEntropy: "Variety of neighboring intensity pairs (entropy)",
  glcm_Id: "Similarity of neighboring intensities (inverse difference)",
  glcm_Idm: "Similarity of neighboring intensities (inverse difference moment)",
  glcm_Idn: "Similarity of neighboring intensities (normalized inverse difference)",
  glcm_Idmn: "Similarity of neighboring intensities (normalized inverse difference moment)",
  glcm_Imc1: "Neighboring intensity dependence (measure 1)",
  glcm_Imc2: "Neighboring intensity dependence (measure 2)",
  glcm_MCC: "Strongest correlation between neighboring intensities",
  firstorder_Energy: "Sum of squared CT intensities",
  firstorder_TotalEnergy: "Sum of squared CT intensities adjusted for volume",
  firstorder_Kurtosis: "How common extreme CT intensities are",
  firstorder_MeanAbsoluteDeviation: "Average distance from the mean CT intensity",
  firstorder_RobustMeanAbsoluteDeviation: "Average spread in the middle 80% of CT intensities",
  firstorder_RootMeanSquared: "Typical size of CT intensity values (root mean square)",
  firstorder_Skewness: "Whether unusually high or low CT intensities are more pronounced",
  firstorder_Variance: "Spread of CT intensities around their average (variance)",
  shape_LeastAxisLength: "Shortest axis of the fitted tumor shape (mm)",
  shape_MajorAxisLength: "Longest axis of the fitted tumor shape (mm)",
  shape_MinorAxisLength: "Middle axis of the fitted tumor shape (mm)",
  shape_Maximum2DDiameterColumn: "Widest distance in a scan column plane (mm)",
  shape_Maximum2DDiameterRow: "Widest distance in a scan row plane (mm)",
  shape_Maximum2DDiameterSlice: "Widest distance on any CT slice (mm)",
  glcm_Autocorrelation: "Average product of neighboring intensity levels",
  glcm_ClusterProminence: "How strongly neighboring intensity sums depart from their average",
  glcm_ClusterShade: "Whether neighboring intensity sums lean high or low",
  glcm_ClusterTendency: "Spread of neighboring intensity sums",
  glcm_DifferenceAverage: "Average difference between neighboring intensities",
  glcm_DifferenceEntropy: "Variety of differences between neighboring intensities",
  glcm_DifferenceVariance: "Spread of differences between neighboring intensities",
  glcm_InverseVariance: "Similarity between neighboring points with different intensities",
  glcm_JointAverage: "Average intensity level in neighboring pairs",
  glcm_JointEnergy: "How concentrated neighboring intensity pairs are",
  glcm_MaximumProbability: "How often the most common neighboring intensity pair occurs",
  glcm_SumAverage: "Average sum of neighboring intensities",
  glcm_SumEntropy: "Variety of neighboring intensity sums",
  glcm_SumSquares: "Spread of intensity levels in neighboring pairs (variance)",
  glrlm_GrayLevelNonUniformity: "How unevenly streaks are spread across intensity levels",
  glrlm_GrayLevelNonUniformityNormalized: "How unevenly streaks are spread across intensity levels, adjusted for streak count",
  glrlm_GrayLevelVariance: "Spread of intensity levels across streaks",
  glrlm_HighGrayLevelRunEmphasis: "How much high-intensity streaks stand out",
  glrlm_LowGrayLevelRunEmphasis: "How much low-intensity streaks stand out",
  glrlm_LongRunEmphasis: "How much long streaks stand out",
  glrlm_LongRunHighGrayLevelEmphasis: "How much long, high-intensity streaks stand out",
  glrlm_LongRunLowGrayLevelEmphasis: "How much long, low-intensity streaks stand out",
  glrlm_ShortRunEmphasis: "How much short streaks stand out",
  glrlm_ShortRunHighGrayLevelEmphasis: "How much short, high-intensity streaks stand out",
  glrlm_ShortRunLowGrayLevelEmphasis: "How much short, low-intensity streaks stand out",
  glrlm_RunEntropy: "Variety of streak lengths and intensity levels",
  glrlm_RunLengthNonUniformity: "How unevenly streaks are spread across lengths",
  glrlm_RunLengthNonUniformityNormalized: "How unevenly streaks are spread across lengths, adjusted for streak count",
  glrlm_RunPercentage: "Number of streaks relative to the number of points measured",
  glrlm_RunVariance: "Spread of streak lengths",
};

const groups: Record<string, string> = {
  firstorder: "CT intensity",
  shape: "Tumor shape",
  glcm: "Neighboring intensities",
  glrlm: "Streaks of similar intensity",
};

export function featureLabel(key: string): string {
  const match = /^original_([^_]+)_(.+)$/.exec(key);
  const name = match?.[2] ?? key;
  const label = name.replace(/_/g, " ")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/([A-Z])([A-Z][a-z])/g, "$1 $2");
  if (!match) return label;
  const family = match[1];
  const group = groups[family];
  return plainNames[`${family}_${name}`] ?? (group ? `${group} — ${label}` : label);
}

const explanations: Record<string, string> = {
  firstorder_10Percentile: "About one in ten points in the tumor have an intensity at or below this value.",
  firstorder_90Percentile: "About nine in ten points in the tumor have an intensity at or below this value.",
  firstorder_Mean: "Add the normalized intensities inside the tumor and divide by the number of points.",
  firstorder_Median: "Sort the intensities inside the tumor and take the value in the middle.",
  firstorder_Minimum: "The darkest point measured inside the tumor on the normalized scan.",
  firstorder_Maximum: "The brightest point measured inside the tumor on the normalized scan.",
  firstorder_Range: "Subtract the lowest tumor intensity from the highest.",
  firstorder_InterquartileRange: "Subtract the intensity at the 25th percentile from the intensity at the 75th percentile.",
  firstorder_Entropy: "Higher values mean the tumor’s points are spread more evenly across different intensity levels.",
  firstorder_Uniformity: "Higher values mean more points share a small number of intensity levels.",
  firstorder_Energy: "Square each point’s intensity and add the results. Larger tumors can have higher values simply because they contain more points.",
  firstorder_TotalEnergy: "Multiply the sum of squared intensities by the volume represented by one point in the scan.",
  firstorder_Kurtosis: "Describes how heavily the intensity distribution is influenced by extreme values.",
  firstorder_MeanAbsoluteDeviation: "Find how far each point is from the average intensity, then average those distances.",
  firstorder_RobustMeanAbsoluteDeviation: "Leave out the darkest and brightest 10%, then average the distances from the remaining points’ mean.",
  firstorder_RootMeanSquared: "Square the intensities, average the squares, and take the square root.",
  firstorder_Skewness: "A positive value means the intensities have a longer tail toward bright values. A negative value means a longer tail toward dark values.",
  firstorder_Variance: "Square each intensity’s distance from the tumor average, then average those squared distances.",
  shape_VoxelVolume: "Count the 3D pixels inside the tumor outline and multiply by the volume of one pixel.",
  shape_MeshVolume: "Estimate the space enclosed by a 3D surface fitted around the tumor outline.",
  shape_SurfaceArea: "Add up the area of the small triangles that form the fitted surface around the tumor.",
  shape_SurfaceVolumeRatio: "Divide the tumor’s surface area by its enclosed volume. A more irregular surface can raise this value.",
  shape_Sphericity: "A value of 1 corresponds to a perfect sphere. Lower values indicate a shape less like a sphere.",
  shape_Elongation: "Compares the middle and longest axes of the fitted shape. Lower values indicate a more stretched shape.",
  shape_Flatness: "Compares the shortest and longest axes of the fitted shape. Lower values indicate a flatter shape.",
  shape_Maximum3DDiameter: "The greatest straight-line distance between any two points on the tumor surface.",
  shape_LeastAxisLength: "The length along the shortest axis of an ellipsoid fitted to the tumor points.",
  shape_MajorAxisLength: "The length along the longest axis of an ellipsoid fitted to the tumor points.",
  shape_MinorAxisLength: "The length along the intermediate axis of an ellipsoid fitted to the tumor points.",
  shape_Maximum2DDiameterColumn: "Find the farthest two surface points in each plane that passes through a scan column, then take the largest distance.",
  shape_Maximum2DDiameterRow: "Find the farthest two surface points in each plane that passes through a scan row, then take the largest distance.",
  shape_Maximum2DDiameterSlice: "Find the farthest two surface points on each slice, then take the largest distance.",
  glcm_Autocorrelation: "Multiply the two intensity levels in each neighboring pair and average the products. Pairs of high intensities contribute more.",
  glcm_ClusterProminence: "Raises each pair sum’s distance from the average to the fourth power, so unusually large departures matter most.",
  glcm_ClusterShade: "Weights departures above and below the average pair sum with opposite signs, revealing which side has the longer tail.",
  glcm_ClusterTendency: "Squares each pair sum’s departure from the average to show how widely pair sums vary.",
  glcm_Contrast: "Weights large intensity differences between adjacent points more heavily than small differences.",
  glcm_Correlation: "A higher positive value means bright points tend to sit near bright points and dark points near dark points.",
  glcm_DifferenceAverage: "Take the absolute difference in intensity level for each neighboring pair, then average it.",
  glcm_DifferenceEntropy: "Higher values mean the size of the intensity difference varies more unpredictably from pair to pair.",
  glcm_DifferenceVariance: "Measures how far the differences between neighboring points typically are from their average difference.",
  glcm_Id: "Gives a pair less weight as the two intensity levels get farther apart.",
  glcm_Idm: "Uses squared differences, reducing the contribution of large intensity gaps more strongly.",
  glcm_Idn: "Scales each pair’s intensity gap by the number of available intensity levels before measuring similarity.",
  glcm_Idmn: "Squares the scaled intensity gap so that large gaps contribute even less to the similarity score.",
  glcm_Imc1: "Compares the variety of intensity pairs with what would be expected if neighboring intensities were independent. Zero indicates independence.",
  glcm_Imc2: "Measures how much knowing one point’s intensity tells you about its neighbor. Zero indicates independence.",
  glcm_InverseVariance: "Counts pairs at different levels, giving small differences greater weight than large differences.",
  glcm_JointAverage: "Averages the first point’s intensity level in the neighboring pairs.",
  glcm_JointEnergy: "Higher values mean a few combinations of neighboring intensities account for most pairs.",
  glcm_JointEntropy: "Higher values mean neighboring points form a wider or more evenly distributed set of intensity combinations.",
  glcm_MCC: "Measures the strongest statistical dependence between the intensities of neighboring points, including nonlinear relationships.",
  glcm_MaximumProbability: "Find the most common combination of neighboring intensity levels and report its share of all pairs.",
  glcm_SumAverage: "Add the two intensity levels in each neighboring pair and average the sums.",
  glcm_SumEntropy: "Higher values mean the sums of neighboring intensity levels are more varied or evenly distributed.",
  glcm_SumSquares: "Measures how far intensity levels in neighboring pairs spread around their average.",
  glrlm_GrayLevelNonUniformity: "Higher values mean more streaks are concentrated in a few intensity levels.",
  glrlm_GrayLevelNonUniformityNormalized: "Measures the concentration of streaks by intensity while accounting for how many streaks were counted.",
  glrlm_GrayLevelVariance: "Higher values mean the streaks cover a wider spread of intensity levels.",
  glrlm_HighGrayLevelRunEmphasis: "Gives extra weight to streaks of bright points, regardless of length.",
  glrlm_LowGrayLevelRunEmphasis: "Gives extra weight to streaks of dark points, regardless of length.",
  glrlm_LongRunEmphasis: "Gives extra weight to long streaks, regardless of intensity.",
  glrlm_LongRunHighGrayLevelEmphasis: "Gives the greatest weight to streaks that are both long and bright.",
  glrlm_LongRunLowGrayLevelEmphasis: "Gives the greatest weight to streaks that are both long and dark.",
  glrlm_ShortRunEmphasis: "Gives extra weight to short streaks, regardless of intensity.",
  glrlm_ShortRunHighGrayLevelEmphasis: "Gives the greatest weight to streaks that are both short and bright.",
  glrlm_ShortRunLowGrayLevelEmphasis: "Gives the greatest weight to streaks that are both short and dark.",
  glrlm_RunEntropy: "Higher values mean there is more variety in the combination of streak length and brightness.",
  glrlm_RunLengthNonUniformity: "Higher values mean many streaks are concentrated at a few lengths.",
  glrlm_RunLengthNonUniformityNormalized: "Measures how concentrated streak lengths are while accounting for how many streaks were counted.",
  glrlm_RunPercentage: "Divide the number of streaks by the number of points. More short streaks give a higher fraction.",
  glrlm_RunVariance: "Higher values mean the scan contains a wider spread of streak lengths.",
};

const normalizedIntensityFeatures = new Set([
  "10Percentile", "90Percentile", "Mean", "Median", "Minimum", "Maximum", "Range",
  "InterquartileRange", "MeanAbsoluteDeviation", "RobustMeanAbsoluteDeviation", "RootMeanSquared",
]);

export function featureDetails(key: string) {
  const label = featureLabel(key);
  const code = key.replace(/^original_/, "");
  const unit = /\((mm[²³]?)\)$/.exec(label)?.[1]
    ?? (code === "shape_SurfaceVolumeRatio" ? "1/mm" : undefined)
    ?? (code === "firstorder_TotalEnergy" ? "mm³ × normalized intensity²" : undefined)
    ?? (code === "firstorder_Variance" || code === "firstorder_Energy" ? "Normalized intensity²" : undefined)
    ?? (code.startsWith("firstorder_") && normalizedIntensityFeatures.has(code.slice(11)) ? "Normalized intensity" : undefined)
    ?? (code.endsWith("Entropy") ? "Bits" : undefined)
    ?? (code === "glrlm_RunPercentage" ? "Fraction" : undefined)
    ?? (explanations[code] ? "Unitless" : "Unit unavailable");
  return {
    label: label.replace(/ \(mm[²³]?\)$/, ""),
    unit,
    explanation: explanations[code] ?? "A detailed definition is unavailable for this saved measurement.",
  };
}
