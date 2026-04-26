// --- Authentication Guard (Fixed Bug) ---
const userJson = localStorage.getItem('user');

if (!userJson) {
    window.location.href = 'login.html';
} else {
    const user = JSON.parse(userJson);
    if (!user || !user.user_id) {
        window.location.href = 'login.html';
    }

    // --- DOM Elements ---
    const welcomeHeader = document.getElementById('welcomeHeader');
    const questList = document.getElementById('questList');
    const logoutBtn = document.getElementById('logoutBtn');
    
    const profileUsername = document.getElementById('profileUsername');
    const profileScore = document.getElementById('profileScore');
    const profileLevel = document.getElementById('profileLevel');
    const nextLevelNum = document.getElementById('nextLevelNum');
    const progressPercent = document.getElementById('progressPercent');
    const progressBarFill = document.getElementById('progressBarFill');

    welcomeHeader.textContent = `Welcome back, ${user.username || 'Reader'}!`;

    // --- Fixed Level Progress Calculation ---
    function calculateProgressToNextLevel(score, level) {
        const milestones = [0, 50, 150, 300, 500, 750];
        if (level >= 6) return { percentage: 100, nextLevelScore: milestones[5] };

        const scoreStartOfCurrentLevel = milestones[level - 1];
        const scoreStartOfNextLevel = milestones[level];
        
        const currentScoreInLevel = score - scoreStartOfCurrentLevel;
        const levelScoreRange = scoreStartOfNextLevel - scoreStartOfCurrentLevel;
        let percentage = (currentScoreInLevel / levelScoreRange) * 100;
        
        return {
            percentage: Math.min(Math.floor(percentage), 99),
            nextLevelScore: scoreStartOfNextLevel
        };
    }

    async function loadUserProfile(leaderboardData) {
        const currentUserData = leaderboardData.find(r => r.username === user.username);
        if (currentUserData) {
            const { score, level } = currentUserData;
            const progress = calculateProgressToNextLevel(score, level);
            
            profileUsername.textContent = user.username;
            profileScore.textContent = score;
            profileLevel.textContent = level;
            nextLevelNum.textContent = level >= 6 ? 'Max' : level + 1;
            progressPercent.textContent = `${progress.percentage}%`;
            progressBarFill.style.width = `${progress.percentage}%`;
        }
    }

    async function completeQuest(questId) {
        const res = await fetch('/complete_quest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: user.user_id, quest_id: questId })
        });
        const data = await res.json();
        if (data.status === 'success') {
            loadQuests();
            loadLeaderboard(); 
        } else {
            alert(`Error: ${data.message}`);
        }
    }
    window.completeQuest = completeQuest;

    async function submitReview(event, questId) {
        event.preventDefault();
        const reviewText = event.target.elements.reviewText.value;
        try {
            const res = await fetch('/submit_review', { 
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: user.user_id, quest_id: questId, submission_text: reviewText })
            });
            const data = await res.json();
            alert(data.message);
            if (data.status === 'success') {
                loadQuests(); 
                loadLeaderboard(); 
            }
        } catch (error) {
            alert('Failed to connect to the server.');
        }
    }
    window.submitReview = submitReview;

    // --- Timer Functions ---
    const TARGET_TIME_MS = 30 * 60 * 1000;
    let timerIntervals = {}; 

    function formatTime(ms) {
        const totalSeconds = Math.floor(ms / 1000);
        return `${String(Math.floor(totalSeconds / 60)).padStart(2, '0')}:${String(totalSeconds % 60).padStart(2, '0')}`;
    }

    function resetTimer(questId) {
        clearInterval(timerIntervals[questId]);
        sessionStorage.removeItem('readingTimer');
        delete timerIntervals[questId];
    }
    window.resetTimer = resetTimer;

    function updateTimerDisplay(questId, remainingTime, endTime) {
        const display = document.getElementById(`timer-${questId}`);
        const button = document.getElementById(`timer-btn-${questId}`);
        if (!display || !button) return;
        
        if (remainingTime <= 0) {
            display.textContent = '00:00';
            button.textContent = 'Claim Points!';
            button.onclick = () => { completeQuest(questId); resetTimer(questId); };
            clearInterval(timerIntervals[questId]);
            sessionStorage.removeItem('readingTimer'); 
        } else {
            display.textContent = formatTime(remainingTime);
        }
    }

    function handleReadingTimer(questId) {
        let timerState = JSON.parse(sessionStorage.getItem('readingTimer') || '{}');
        const button = document.getElementById(`timer-btn-${questId}`);

        if (timerState.running && timerState.questId !== questId) {
            alert("Please pause the current reading timer before starting a new one.");
            return;
        }

        if (timerState.running && timerState.questId === questId) {
            clearInterval(timerIntervals[questId]);
            button.textContent = 'Resume Reading';
            timerState.running = false;
            timerState.totalTimeElapsed += (Date.now() - timerState.startTime);
            sessionStorage.setItem('readingTimer', JSON.stringify(timerState));
            updateTimerDisplay(questId, TARGET_TIME_MS - timerState.totalTimeElapsed);
        } else {
            button.textContent = 'Pause Reading';
            const totalTimeElapsed = timerState.totalTimeElapsed || 0;
            const now = Date.now();
            timerState = { questId, running: true, startTime: now, endTime: now + TARGET_TIME_MS - totalTimeElapsed, totalTimeElapsed };
            sessionStorage.setItem('readingTimer', JSON.stringify(timerState));
            
            timerIntervals[questId] = setInterval(() => {
                const remainingTime = Math.max(0, timerState.endTime - Date.now());
                timerState.totalTimeElapsed = TARGET_TIME_MS - remainingTime;
                sessionStorage.setItem('readingTimer', JSON.stringify(timerState));
                updateTimerDisplay(questId, remainingTime, timerState.endTime);
            }, 1000);
            updateTimerDisplay(questId, timerState.endTime - Date.now(), timerState.endTime);
        }
    }
    window.handleReadingTimer = handleReadingTimer; 

    // --- Loading Data ---
    async function loadQuests() {
        questList.innerHTML = '<li>Loading quests...</li>';
        try {
            const res = await fetch(`/quests?user_id=${user.user_id}`);
            const quests = await res.json();
            questList.innerHTML = '';

            const timerState = JSON.parse(sessionStorage.getItem('readingTimer') || '{}');
            
            quests.forEach(quest => {
                const li = document.createElement('li');
                li.className = 'quest-item';
                let actionContent = '';
                
                if (quest.completed_today) {
                    actionContent = `<span class="completed-tag">Completed Today</span>`;
                } else if (quest.title.toLowerCase().includes("review")) { 
                    actionContent = `
                        <form class="quest-submission-form" onsubmit="submitReview(event, ${quest.id})">
                            <textarea name="reviewText" placeholder="Write your review here (50-500 chars)..." required minlength="50" maxlength="500" class="review-textarea" style="width:100%; border-radius:5px; padding:5px; margin-bottom:5px;"></textarea>
                            <button type="submit" class="submit-btn complete-btn">Submit Review</button>
                        </form>`;
                } else if (quest.title.toLowerCase().includes("30 minutes")) {
                    let timeRemaining = TARGET_TIME_MS;
                    let buttonText = 'Start Reading';
                    let isRunning = false;
                    
                    if (timerState.questId === quest.id) {
                        isRunning = timerState.running;
                        timeRemaining = isRunning ? Math.max(0, timerState.endTime - Date.now()) : Math.max(0, TARGET_TIME_MS - timerState.totalTimeElapsed); 
                        buttonText = isRunning ? 'Pause Reading' : 'Resume Reading';
                    }
                    
                    if (timeRemaining <= 0) {
                        actionContent = `<button class="complete-btn" onclick="completeQuest(${quest.id}); resetTimer(${quest.id})">Claim Points!</button>`;
                    } else {
                        actionContent = `
                            <div class="timer-container" style="display:flex; align-items:center; gap:10px;">
                                <span id="timer-${quest.id}" class="timer-display" style="font-weight:bold;">${formatTime(timeRemaining)}</span>
                                <button class="complete-btn" id="timer-btn-${quest.id}" onclick="handleReadingTimer(${quest.id})">${buttonText}</button>
                            </div>`;
                        if (isRunning) handleReadingTimer(quest.id); 
                    }
                } else {
                    actionContent = `<button class="complete-btn" onclick="completeQuest(${quest.id})">Complete Quest</button>`;
                }

                li.innerHTML = `
                    <div class="quest-info">
                        <h3>${quest.title}</h3>
                        <p>${quest.description}</p>
                    </div>
                    <div style="display:flex; align-items:center;">
                        <span class="quest-points">+${quest.points} pts</span>
                        <div class="quest-action">${actionContent}</div>
                    </div>`;
                questList.appendChild(li);
            });
        } catch (error) {
            questList.innerHTML = `<li>Error loading quests.</li>`;
        }
    }

    async function loadLeaderboard() {
        const res = await fetch('/leaderboard');
        const rows = await res.json();
        const tbody = document.querySelector('#leaderboardTable tbody');
        tbody.innerHTML = '';
        loadUserProfile(rows);

        rows.forEach((r, i) => {
            const tr = document.createElement('tr');
            if (r.username === user.username) {
                tr.style.backgroundColor = 'rgba(0, 255, 255, 0.1)'; 
            }
            tr.innerHTML = `<td>${i + 1}</td><td>${r.username}</td><td>${r.score}</td><td>${r.level}</td>`;
            tbody.appendChild(tr);
        });
    }

    // --- AI Matchmaker Event (IDEA 2) ---
    const getRecommendationsBtn = document.getElementById('getRecommendationsBtn');
    const recommendationsOutput = document.getElementById('recommendationsOutput');
    if (getRecommendationsBtn) {
        getRecommendationsBtn.addEventListener('click', async () => {
            recommendationsOutput.innerHTML = "<em>Consulting the AI library...</em>";
            getRecommendationsBtn.disabled = true;
            try {
                const res = await fetch(`/recommendations?user_id=${user.user_id}`);
                const data = await res.json();
                if (data.status === 'success') {
                    recommendationsOutput.textContent = data.recommendations;
                } else {
                    recommendationsOutput.innerHTML = `<span style="color: #e74c3c;">${data.message}</span>`;
                }
            } catch (err) {
                recommendationsOutput.innerHTML = `<span style="color: #e74c3c;">Error reaching AI.</span>`;
            } finally {
                getRecommendationsBtn.disabled = false;
            }
        });
    }

    // --- AI Surprise Quest Event (IDEA 3) ---
    const generateQuestBtn = document.getElementById('generateQuestBtn');
    if (generateQuestBtn) {
        generateQuestBtn.addEventListener('click', async () => {
            generateQuestBtn.textContent = "Generating...";
            generateQuestBtn.disabled = true;
            try {
                const res = await fetch('/generate_surprise_quest', { method: 'POST' });
                const data = await res.json();
                if (data.status === 'success') {
                    loadQuests(); // Refresh the list to show the new quest at the top!
                } else {
                    alert(data.message);
                }
            } catch (err) {
                alert("Failed to reach AI server.");
            } finally {
                generateQuestBtn.textContent = "✨ Generate AI Quest";
                generateQuestBtn.disabled = false;
            }
        });
    }

    logoutBtn.addEventListener('click', () => {
        localStorage.removeItem('user');
        sessionStorage.removeItem('readingTimer');
        window.location.href = 'login.html';
    });

    document.getElementById('achievementsBtn').addEventListener('click', () => window.location.href = 'achievement.html');
    document.getElementById('feedsBtn').addEventListener('click', () => window.location.href = 'feedsbtn.html');

    window.onload = function() {
        loadQuests();
        loadLeaderboard();
    };
}