Write-Host "Pushing Firebase Credentials..."
vercel env rm FIREBASE_CREDENTIALS production -y 2>$null
$firebaseJson = Get-Content "firebase_key.json" -Raw
$firebaseJson | vercel env add FIREBASE_CREDENTIALS production

Write-Host "Pushing .env Variables..."
$envContent = Get-Content ".env"
foreach ($line in $envContent) {
    $line = $line.Trim()
    if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("#")) { continue }
    
    if ($line -match '^([^=]+)=(.*)$') {
        $key = $matches[1].Trim()
        $val = $matches[2].Trim().Trim('"', "'")
        
        Write-Host "Adding $key..."
        vercel env rm $key production -y 2>$null
        Write-Output $val | vercel env add $key production
    }
}

Write-Host "All configuration credentials successfully uploaded to Vercel!"
Write-Host "You should now redeploy your app on Vercel so it can pick them up: vercel --prod"
