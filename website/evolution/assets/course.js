(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  // Deterministic random numbers make simulations discussable and replayable.
  function mulberry32(seed) {
    return function () {
      let t = seed += 0x6D2B79F5;
      t = Math.imul(t ^ t >>> 15, t | 1);
      t ^= t + Math.imul(t ^ t >>> 7, t | 61);
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }
  function binomial(n, p, random) {
    let successes = 0;
    for (let i = 0; i < n; i++) if (random() < p) successes++;
    return successes;
  }

  $$('.quiz').forEach(quiz => {
    const feedback = $('.feedback', quiz);
    $$('.choice', quiz).forEach(choice => choice.addEventListener('click', () => {
      $$('.choice', quiz).forEach(c => { c.classList.remove('correct', 'incorrect'); c.disabled = true; });
      const correct = choice.dataset.correct === 'true';
      choice.classList.add(correct ? 'correct' : 'incorrect');
      if (!correct) {
        const answer = $('.choice[data-correct="true"]', quiz);
        if (answer) answer.classList.add('correct');
      }
      feedback.textContent = correct ? choice.dataset.feedback : (choice.dataset.feedback || quiz.dataset.retry || 'Not quite—compare the causal mechanisms.');
      feedback.className = `feedback ${correct ? 'good' : 'try'}`;
    }));
    const reset = $('.quiz-reset', quiz);
    if (reset) reset.addEventListener('click', () => {
      $$('.choice', quiz).forEach(c => { c.classList.remove('correct', 'incorrect'); c.disabled = false; });
      feedback.textContent = '';
    });
  });

  const beetleGame = $('#beetle-game');
  if (beetleGame) {
    const field = $('.beetle-field', beetleGame);
    const feedback = $('.feedback', beetleGame);
    let dark = 20, light = 20, generation = 0, seed = 37;
    function render() {
      field.innerHTML = '';
      for (let i = 0; i < dark + light; i++) {
        const bug = document.createElement('span');
        bug.className = `beetle ${i < dark ? 'dark' : 'light'}`;
        bug.setAttribute('aria-hidden', 'true');
        field.appendChild(bug);
      }
      $('.dark-count', beetleGame).textContent = dark;
      $('.light-count', beetleGame).textContent = light;
      $('.generation', beetleGame).textContent = generation;
      field.setAttribute('aria-label', `Generation ${generation}: ${dark} dark beetles and ${light} light beetles.`);
    }
    $('.advance', beetleGame).addEventListener('click', () => {
      const darkHabitat = $('#habitat', beetleGame).value === 'dark';
      const random = mulberry32(seed + generation++);
      const darkWeight = dark * (darkHabitat ? 1.45 : 0.7);
      const lightWeight = light * (darkHabitat ? 0.7 : 1.45);
      const darkProbability = darkWeight / (darkWeight + lightWeight);
      dark = binomial(40, darkProbability, random);
      light = 40 - dark;
      feedback.textContent = `Selection changed reproductive odds; sampling added chance. No beetle changed color because it “needed” to.`;
      render();
    });
    $('.mutate', beetleGame).addEventListener('click', () => {
      const random = mulberry32(seed + generation * 101 + dark * 17);
      const lightToDark = light > 0 && (dark === 0 || random() < 0.5);
      if (lightToDark) { light--; dark++; } else if (dark > 0) { dark--; light++; }
      feedback.textContent = `One randomly chosen mutation direction changed a ${lightToDark ? 'light beetle to dark' : 'dark beetle to light'}. The habitat was not consulted.`;
      render();
    });
    $('.reset-sim', beetleGame).addEventListener('click', () => { dark = light = 20; generation = 0; seed++; feedback.textContent = ''; render(); });
    $('#habitat', beetleGame).addEventListener('change', e => { field.style.background = e.target.value === 'dark' ? '#625d55' : '#d6c3a1'; });
    render();
  }

  const driftLab = $('#drift-lab');
  if (driftLab) {
    const chart = $('.chart', driftLab);
    const population = $('#population', driftLab);
    const selection = $('#selection', driftLab);
    const migration = $('#migration', driftLab);
    const seedInput = $('#seed', driftLab);
    [population, selection, migration, seedInput].forEach(input => input.addEventListener('input', () => {
      $(`[data-value="${input.id}"]`, driftLab).textContent = input.value;
    }));
    function run() {
      const n = +population.value, s = +selection.value, m = +migration.value, seed = +seedInput.value;
      const paths = [];
      for (let replicate = 0; replicate < 12; replicate++) {
        const random = mulberry32(seed + replicate * 991);
        const values = [0.5];
        for (let g = 1; g <= 40; g++) {
          let p = values[g - 1];
          p = (p * (1 + s)) / (1 + p * s); // selection
          p = p * (1 - m) + 0.8 * m;       // migrants carry p=.8
          p = binomial(n, p, random) / n;   // haploid Wright–Fisher sampling
          values.push(p);
        }
        paths.push(values);
      }
      draw(paths);
      const end = paths.map(p => p.at(-1));
      const lost = end.filter(p => p === 0).length;
      const fixed = end.filter(p => p === 1).length;
      $('.sim-summary', driftLab).textContent = `After 40 generations: range ${Math.min(...end).toFixed(2)}–${Math.max(...end).toFixed(2)}; mean ${(end.reduce((a,b)=>a+b,0)/end.length).toFixed(2)}; ${lost} lost A and ${fixed} fixed A. Same assumptions, different chance histories.`;
      const checkpoints = [0, 10, 20, 30, 40];
      $('.drift-table-body', driftLab).innerHTML = paths.map((path, i) => `<tr><th scope="row">${i + 1}${i === 0 ? ' (highlighted)' : ''}</th>${checkpoints.map(g => `<td>${path[g].toFixed(2)}</td>`).join('')}</tr>`).join('');
    }
    function draw(paths) {
      const width = 760, height = 230, pad = 28;
      chart.setAttribute('viewBox', `0 0 ${width} ${height}`);
      chart.innerHTML = `<line class="chart-axis" x1="${pad}" y1="${height-pad}" x2="${width-8}" y2="${height-pad}"/><line class="chart-axis" x1="${pad}" y1="8" x2="${pad}" y2="${height-pad}"/><line class="chart-grid" x1="${pad}" y1="${height/2}" x2="${width-8}" y2="${height/2}"/><text class="chart-label" x="4" y="15">1.0</text><text class="chart-label" x="8" y="${height-pad}">0</text><text class="chart-label" x="${width-85}" y="${height-8}">generation 40</text>`;
      paths.forEach((path, i) => {
        const points = path.map((p, g) => `${pad + g * (width-pad-8)/40},${8 + (1-p)*(height-pad-8)}`).join(' ');
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
        line.setAttribute('points', points); line.setAttribute('fill', 'none');
        line.setAttribute('stroke', i === 0 ? '#176b58' : '#b7b5af');
        line.setAttribute('stroke-width', i === 0 ? '2.5' : '1');
        chart.appendChild(line);
      });
    }
    $('.run-drift', driftLab).addEventListener('click', run);
    run();
  }

  $$('.channel-game').forEach(game => {
    const feedback = $('.feedback', game);
    $$('.channel', game).forEach(button => button.addEventListener('click', () => {
      $$('.channel', game).forEach(b => b.classList.remove('selected'));
      button.classList.add('selected');
      const correct = button.dataset.correct === 'true';
      feedback.textContent = correct ? button.dataset.feedback : button.dataset.feedback;
      feedback.className = `feedback ${correct ? 'good' : 'try'}`;
    }));
  });

  let stored = {};
  try {
    stored = JSON.parse(localStorage.getItem('evolution-course-progress') || '{}');
    if (!stored || typeof stored !== 'object' || Array.isArray(stored)) stored = {};
    const lesson = document.body.dataset.lesson;
    if (lesson) {
      stored[lesson] = { visited: true, date: new Date().toISOString().slice(0, 10) };
      localStorage.setItem('evolution-course-progress', JSON.stringify(stored));
    }
  } catch (_) {
    stored = {}; // Progress is optional; lessons and activities still work without storage.
  }
  $$('[data-progress]').forEach(el => {
    const count = Object.values(stored).filter(item => item && item.visited).length;
    el.textContent = `${count} of 6 lessons visited on this device`;
  });
})();
